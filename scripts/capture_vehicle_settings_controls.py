#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.vehicle_settings_icon_mapping_config import PAGE_TREE


ADB = "adb"
ADB_SERIAL: str | None = None
HOME_PACKAGE = "com.autolink.launcher"
VEHICLE_PACKAGE = "com.autolink.vehicle"
RESOLVER_PACKAGE = "com.android.car.activityresolver"
REMOTE_XML = "/sdcard/vehicle_settings_capture.xml"
REMOTE_PNG = "/sdcard/vehicle_settings_capture.png"
WAIT_AFTER_TAP = 1.2
WAIT_AFTER_HOME = 1.2
WAIT_AFTER_SWIPE = 0.9
DEFAULT_EXPORT_MIN_WIDTH = 56
DEFAULT_EXPORT_MIN_HEIGHT = 36
DEFAULT_SCROLL = (2110, 1220, 2110, 360, 420)
DEFAULT_ENTRY_TAP = (1210, 1383)
LEFT_MENU_SCROLL_DOWN = (200, 1180, 200, 260, 420)
LEFT_MENU_SCROLL_UP = (200, 260, 200, 1180, 420)
EDGE_MARGIN_BOTTOM = 120
EDGE_MARGIN_TOP = 24

SKIP_RESOURCE_IDS = {
    "android:id/content",
    "com.autolink.vehicle:id/main",
    "com.autolink.vehicle:id/nsb_main_tab",
    "com.autolink.vehicle:id/fm_container",
    "com.autolink.vehicle:id/fragment_container",
    "com.autolink.vehicle:id/scroll_view",
    "com.autolink.vehicle:id/general_scroll_view",
    "com.autolink.vehicle:id/cl_root",
    "com.autolink.vehicle:id/text_container",
    "com.autolink.vehicle:id/tabLayout",
    "com.autolink.vehicle:id/layout_energy_manager",
    "com.autolink.vehicle:id/energy_consumption_bg",
    "com.autolink.vehicle:id/energy_consumption_chat",
    "com.autolink.vehicle:id/range_and_battery_group",
    "com.autolink.vehicle:id/consumption_empty",
    "com.autolink.vehicle:id/range_display_mode_selector",
    "com.autolink.vehicle:id/recovery_level_selector",
    "com.autolink.vehicle:id/car_model_view",
    "com.autolink.vehicle:id/car_model_default0",
}


@dataclass(frozen=True)
class Selector:
    resource_id: str | None = None
    text: str | None = None
    text_contains: str | None = None
    clickable_only: bool = False


@dataclass(frozen=True)
class PageSpec:
    page_key: str
    parent_key: str | None
    selectors: tuple[Selector, ...]
    expected_texts: tuple[str, ...] = ()
    expected_resource_ids: tuple[str, ...] = ()
    max_scrolls: int = 0


PAGE_INDEX = {item["page_key"]: item for item in PAGE_TREE}
DEFAULT_PAGE_ORDER = [item["page_key"] for item in PAGE_TREE if item["page_key"] in {
    "vehicle_root",
    "vehicle_common",
    "vehicle_door_lock",
    "energy_root",
    "energy_charge",
    "energy_manage",
    "light_root",
    "light_exterior",
    "display_root",
    "sound_root",
    "connection_root",
    "general_root",
}]
PAGE_SPECS: dict[str, PageSpec] = {
    "vehicle_root": PageSpec(
        page_key="vehicle_root",
        parent_key=None,
        selectors=(),
        expected_texts=("设置车辆未选中", "车辆"),
        expected_resource_ids=("com.autolink.vehicle:id/vehicle",),
    ),
    "vehicle_common": PageSpec(
        page_key="vehicle_common",
        parent_key="vehicle_root",
        selectors=(Selector(text="常用"), Selector(text_contains="常用"),),
        expected_texts=("常用", "中控锁", "前舱盖解锁"),
        max_scrolls=1,
    ),
    "vehicle_door_lock": PageSpec(
        page_key="vehicle_door_lock",
        parent_key="vehicle_root",
        selectors=(Selector(text="门窗锁"), Selector(text="车门锁"), Selector(text_contains="门窗"),),
        expected_texts=("门窗锁", "车门锁"),
        max_scrolls=1,
    ),
    "energy_root": PageSpec(
        page_key="energy_root",
        parent_key="vehicle_root",
        selectors=(Selector(resource_id="com.autolink.vehicle:id/energy"), Selector(text="能量"),),
        expected_texts=("能量",),
    ),
    "energy_charge": PageSpec(
        page_key="energy_charge",
        parent_key="energy_root",
        selectors=(Selector(text="充放电管理"), Selector(text_contains="充电"),),
        expected_texts=("充放电管理",),
        max_scrolls=1,
    ),
    "energy_manage": PageSpec(
        page_key="energy_manage",
        parent_key="energy_root",
        selectors=(Selector(text="能量管理"), Selector(text="能耗信息"), Selector(text_contains="能量回收"),),
        expected_texts=("能量管理", "能耗信息"),
        max_scrolls=1,
    ),
    "light_root": PageSpec(
        page_key="light_root",
        parent_key="vehicle_root",
        selectors=(Selector(resource_id="com.autolink.vehicle:id/terior_light"), Selector(text="灯光"),),
        expected_texts=("灯光",),
    ),
    "light_exterior": PageSpec(
        page_key="light_exterior",
        parent_key="light_root",
        selectors=(Selector(text="车外灯"), Selector(text_contains="位置灯"),),
        expected_texts=("车外灯", "位置灯"),
        max_scrolls=1,
    ),
    "display_root": PageSpec(
        page_key="display_root",
        parent_key="vehicle_root",
        selectors=(Selector(text="显示"), Selector(text="屏幕"),),
        expected_texts=("显示", "屏幕"),
        max_scrolls=2,
    ),
    "sound_root": PageSpec(
        page_key="sound_root",
        parent_key="vehicle_root",
        selectors=(Selector(resource_id="com.autolink.vehicle:id/sound"), Selector(text="声音"),),
        expected_texts=("声音", "声音控制"),
        max_scrolls=1,
    ),
    "connection_root": PageSpec(
        page_key="connection_root",
        parent_key="vehicle_root",
        selectors=(Selector(text="连接"), Selector(text="无线连接"),),
        expected_texts=("连接", "无线连接"),
        max_scrolls=1,
    ),
    "general_root": PageSpec(
        page_key="general_root",
        parent_key="vehicle_root",
        selectors=(Selector(text="通用"), Selector(text="恢复出厂设置"),),
        expected_texts=("通用", "恢复出厂设置"),
        max_scrolls=1,
    ),
}


def run_adb(args: list[str]) -> str:
    cmd = [ADB]
    if ADB_SERIAL:
        cmd.extend(["-s", ADB_SERIAL])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result.stdout


def keyevent(code: str) -> None:
    run_adb(["shell", "input", "keyevent", code])


def tap(x: int, y: int) -> None:
    run_adb(["shell", "input", "tap", str(x), str(y)])


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
    run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])


def current_focus() -> str:
    out = run_adb(["shell", "dumpsys", "window"])
    focus_lines = [line.strip() for line in out.splitlines() if "mCurrentFocus" in line]
    return focus_lines[-1] if focus_lines else ""


def focus_package(focus: str) -> str:
    match = re.search(r"\s([A-Za-z0-9._]+)/", focus)
    return match.group(1) if match else ""


def ensure_home() -> None:
    package = focus_package(current_focus())
    if package != HOME_PACKAGE:
        keyevent("3")
        time.sleep(WAIT_AFTER_HOME)
        if focus_package(current_focus()) == RESOLVER_PACKAGE:
            resolve_home_chooser()
            time.sleep(WAIT_AFTER_HOME)


def parse_bounds(text: str) -> tuple[int, int, int, int]:
    match = re.match(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$", text)
    if not match:
        raise ValueError(text)
    return tuple(int(value) for value in match.groups())


def parse_xml(xml_path: Path) -> list[dict[str, Any]]:
    root = ET.parse(xml_path).getroot()
    rows: list[dict[str, Any]] = []
    for node in root.iter("node"):
        bounds = node.attrib.get("bounds", "")
        if not bounds:
            continue
        try:
            left, top, right, bottom = parse_bounds(bounds)
        except ValueError:
            continue
        rows.append(
            {
                "text": node.attrib.get("text", "").strip(),
                "content_desc": node.attrib.get("content-desc", "").strip(),
                "resource_id": node.attrib.get("resource-id", "").strip(),
                "class": node.attrib.get("class", "").strip(),
                "package": node.attrib.get("package", "").strip(),
                "clickable": node.attrib.get("clickable", "").strip(),
                "checkable": node.attrib.get("checkable", "").strip(),
                "checked": node.attrib.get("checked", "").strip(),
                "enabled": node.attrib.get("enabled", "").strip(),
                "focusable": node.attrib.get("focusable", "").strip(),
                "scrollable": node.attrib.get("scrollable", "").strip(),
                "bounds": bounds,
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "width": right - left,
                "height": bottom - top,
                "center_x": (left + right) // 2,
                "center_y": (top + bottom) // 2,
            }
        )
    return rows


def classify_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rid_blob = "\n".join(row["resource_id"] for row in rows).lower()
    text_blob = "\n".join(filter(None, (row["text"] for row in rows))).lower()
    packages = [row["package"] for row in rows if row["package"]]
    package = max(set(packages), key=packages.count) if packages else ""
    scores = {"home": 0, "vehicle_settings": 0, "other": 0}
    reasons: list[str] = []
    if package == HOME_PACKAGE:
        scores["home"] += 8
        reasons.append("package=com.autolink.launcher")
    if package == VEHICLE_PACKAGE:
        scores["vehicle_settings"] += 10
        reasons.append("package=com.autolink.vehicle")
    if "com.autolink.vehicle:id/" in rid_blob:
        scores["vehicle_settings"] += 8
        reasons.append("vehicle settings resource ids present")
    if any(key in rid_blob for key in ("id/vehicle", "id/energy", "id/assistive_driving", "id/sound", "id/terior_light")):
        scores["vehicle_settings"] += 6
        reasons.append("vehicle settings menu ids present")
    if any(key in rid_blob for key in ("launcher_root", "widget_bottom", "rv_widget_list")):
        scores["home"] += 8
        reasons.append("launcher home ids present")
    if "车辆设置" in text_blob:
        scores["vehicle_settings"] += 2
        reasons.append("vehicle settings text present")
    page_type = max(scores, key=scores.get)
    return {
        "package": package,
        "page_type": page_type,
        "confidence": scores[page_type],
        "scores": scores,
        "reasons": reasons,
    }


def capture_page(output_dir: Path, display_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    xml_path = output_dir / "ui.xml"
    png_path = output_dir / "screen.png"
    run_adb(["shell", "uiautomator", "dump", REMOTE_XML])
    try:
        run_adb(["shell", "screencap", "-d", display_id, "-p", REMOTE_PNG])
    except RuntimeError:
        # Some head units expose multiple displays but only allow stable capture
        # from the default internal screen when `-d` is omitted.
        run_adb(["shell", "screencap", "-p", REMOTE_PNG])
    run_adb(["pull", REMOTE_XML, str(xml_path)])
    run_adb(["pull", REMOTE_PNG, str(png_path)])
    rows = parse_xml(xml_path)
    info = classify_rows(rows)
    (output_dir / "ui_nodes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "ui_nodes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    meta_dir = output_dir / "_meta"
    meta_dir.mkdir(exist_ok=True)
    (meta_dir / "page_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows, info


def capture_current_rows(temp_name: str = "_temp_current_page") -> list[dict[str, Any]]:
    temp_dir = ROOT / "out" / temp_name
    xml_path = temp_dir / "ui.xml"
    temp_dir.mkdir(parents=True, exist_ok=True)
    run_adb(["shell", "uiautomator", "dump", REMOTE_XML])
    run_adb(["pull", REMOTE_XML, str(xml_path)])
    return parse_xml(xml_path)


def resolve_home_chooser() -> None:
    rows = capture_current_rows("_temp_home_chooser")
    target = (
        find_best_match(rows, (Selector(resource_id="android:id/button_always"), Selector(text="始终"),))
        or find_best_match(rows, (Selector(resource_id="android:id/button_once"), Selector(text="仅此一次"),))
    )
    if not target:
        raise RuntimeError("Unable to resolve home chooser automatically")
    tap(target["center_x"], target["center_y"])


def load_entry_tap() -> tuple[int, int]:
    manifest_path = ROOT / "press_android" / "label_pic" / "screen_manifest.json"
    if not manifest_path.exists():
        return DEFAULT_ENTRY_TAP
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_ENTRY_TAP
    entry = manifest.get("首页", {}).get("车辆设置")
    if isinstance(entry, dict) and "x" in entry and "y" in entry:
        return int(entry["x"]), int(entry["y"])
    return DEFAULT_ENTRY_TAP


def score_selector(row: dict[str, Any], selector: Selector) -> int:
    score = 0
    if selector.resource_id:
        if row["resource_id"] != selector.resource_id:
            return -1
        score += 40
    label_blob = " ".join(part for part in (row["text"], row["content_desc"]) if part)
    if selector.text:
        if selector.text not in label_blob:
            return -1
        score += 25 if label_blob == selector.text else 18
    if selector.text_contains:
        if selector.text_contains not in label_blob:
            return -1
        score += 10
    if selector.clickable_only and row["clickable"] != "true":
        return -1
    if row["clickable"] == "true":
        score += 6
    if row["enabled"] == "true":
        score += 4
    score += min(row["width"] // 40, 5)
    return score


def find_best_match(rows: list[dict[str, Any]], selectors: tuple[Selector, ...]) -> dict[str, Any] | None:
    best: tuple[int, dict[str, Any]] | None = None
    for row in rows:
        for selector in selectors:
            score = score_selector(row, selector)
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, row)
    return best[1] if best else None


def is_expected_page(rows: list[dict[str, Any]], spec: PageSpec) -> bool:
    text_set = {row["text"] for row in rows if row["text"]}
    resource_ids = {row["resource_id"] for row in rows if row["resource_id"]}
    if any(text in text_set for text in spec.expected_texts):
        return True
    if any(resource_id in resource_ids for resource_id in spec.expected_resource_ids):
        return True
    return False


def ensure_vehicle_root(display_id: str, session_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ensure_home()
    tap_x, tap_y = load_entry_tap()
    tap(tap_x, tap_y)
    time.sleep(WAIT_AFTER_TAP)
    root_dir = session_dir / "vehicle_root"
    rows, info = capture_page(root_dir, display_id)
    if info["package"] != VEHICLE_PACKAGE:
        raise RuntimeError(f"Vehicle settings entry did not open expected package: {info['package']}")
    return rows, info


def export_controls(page_dir: Path, rows: list[dict[str, Any]], logical_page_key: str | None = None) -> list[dict[str, Any]]:
    image = Image.open(page_dir / "screen.png").convert("RGBA")
    export_dir = page_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    manifest: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    seen_label_bounds: set[tuple[str, tuple[int, int, int, int]]] = set()
    for row in rows:
        if row["package"] != VEHICLE_PACKAGE:
            continue
        if row["enabled"] != "true":
            continue
        if row["width"] < DEFAULT_EXPORT_MIN_WIDTH or row["height"] < DEFAULT_EXPORT_MIN_HEIGHT:
            continue
        if not is_export_candidate(row, image.size, logical_page_key):
            continue
        signature = (row["resource_id"], row["text"], row["bounds"])
        if signature in seen:
            continue
        if is_semantic_duplicate(row, seen_label_bounds):
            continue
        seen.add(signature)
        crop = image.crop((row["left"], row["top"], row["right"], row["bottom"]))
        file_name = sanitize_name(build_control_name(row, len(manifest) + 1))
        out_path = unique_output_path(export_dir, file_name)
        crop.save(out_path)
        semantic_label = normalized_semantic_label(row)
        if semantic_label:
            seen_label_bounds.add((semantic_label, (row["left"], row["top"], row["right"], row["bottom"])))
        manifest.append(
            {
                "name": out_path.stem,
                "text": row["text"],
                "content_desc": row["content_desc"],
                "resource_id": row["resource_id"],
                "class": row["class"],
                "bounds": row["bounds"],
                "clickable": row["clickable"],
                "checkable": row["checkable"],
                "checked": row["checked"],
                "output": str(out_path),
            }
        )
    (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def is_export_candidate(row: dict[str, Any], image_size: tuple[int, int], logical_page_key: str | None) -> bool:
    image_width, image_height = image_size
    combo = f"{row['resource_id']} {row['text']} {row['content_desc']} {row['class']}".lower()
    if any(bad in combo for bad in ("back", "home", "titlebar", "statusbar")):
        return False
    if row["resource_id"] in SKIP_RESOURCE_IDS:
        return False
    if row["width"] >= int(image_width * 0.72) and row["height"] >= int(image_height * 0.45):
        return False
    if row["top"] <= EDGE_MARGIN_TOP and row["height"] < 64:
        return False
    # Text-only short controls near the viewport bottom tend to be partially visible slices.
    if (
        row["text"]
        and not row["resource_id"]
        and row["height"] <= 56
        and row["bottom"] >= image_height - EDGE_MARGIN_BOTTOM
    ):
        return False
    if logical_page_key and logical_page_key.startswith("energy_"):
        if row["resource_id"].endswith((":layout_energy_manager", ":energy_consumption_bg", ":energy_consumption_chat")):
            return False
    if row["clickable"] == "true" or row["checkable"] == "true":
        return True
    if any(key in row["class"] for key in ("Switch", "SeekBar", "CheckBox", "RadioButton")):
        return True
    if row["text"] and row["width"] >= 180:
        return True
    if row["resource_id"] and row["width"] >= 80 and row["height"] >= 60:
        return True
    return False


def is_semantic_duplicate(row: dict[str, Any], seen_label_bounds: set[tuple[str, tuple[int, int, int, int]]]) -> bool:
    semantic_label = normalized_semantic_label(row)
    if not semantic_label:
        return False
    current = (row["left"], row["top"], row["right"], row["bottom"])
    for label, prev in seen_label_bounds:
        if label != semantic_label:
            continue
        if contains(prev, current) or contains(current, prev):
            return True
    return False


def normalized_semantic_label(row: dict[str, Any]) -> str:
    label = (row.get("text") or row.get("content_desc") or "").strip()
    return label


def contains(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def build_control_name(row: dict[str, Any], index: int) -> str:
    if row["text"]:
        return row["text"]
    if row["content_desc"]:
        return row["content_desc"]
    if row["resource_id"]:
        return row["resource_id"].split("/")[-1]
    return f"control_{index:03d}"


def sanitize_name(text: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*]+", "_", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned or "control"


def unique_output_path(export_dir: Path, base_name: str) -> Path:
    candidate = export_dir / f"{base_name}.png"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = export_dir / f"{base_name}_{index}.png"
        if not candidate.exists():
            return candidate
        index += 1


def scroll_once() -> None:
    swipe(*DEFAULT_SCROLL)
    time.sleep(WAIT_AFTER_SWIPE)


def scroll_left_menu(direction: str) -> None:
    if direction == "down":
        swipe(*LEFT_MENU_SCROLL_DOWN)
    elif direction == "up":
        swipe(*LEFT_MENU_SCROLL_UP)
    else:
        raise ValueError(direction)
    time.sleep(WAIT_AFTER_SWIPE)


def search_in_left_menu(
    selectors: tuple[Selector, ...],
    display_id: str,
    temp_root: Path,
    attempts_each_direction: int = 3,
) -> dict[str, Any] | None:
    rows, _ = capture_page(temp_root / "left_menu_probe_current", display_id)
    target = find_best_match(rows, selectors)
    if target:
        return target

    for idx in range(attempts_each_direction):
        scroll_left_menu("up")
        rows, _ = capture_page(temp_root / f"left_menu_probe_up_{idx:02d}", display_id)
        target = find_best_match(rows, selectors)
        if target:
            return target

    for idx in range(attempts_each_direction):
        scroll_left_menu("down")
        rows, _ = capture_page(temp_root / f"left_menu_probe_down_{idx:02d}", display_id)
        target = find_best_match(rows, selectors)
        if target:
            return target
    return None


def capture_page_variants(page_key: str, rows: list[dict[str, Any]], display_id: str, session_dir: Path) -> list[dict[str, Any]]:
    spec = PAGE_SPECS[page_key]
    variants: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for viewport in range(spec.max_scrolls + 1):
        viewport_dir = session_dir / page_key / f"viewport_{viewport:02d}"
        current_rows, info = capture_page(viewport_dir, display_id) if viewport > 0 else (rows, classify_rows(rows))
        if viewport == 0:
            export_manifest = export_controls(session_dir / page_key, current_rows, page_key)
        else:
            export_manifest = export_controls(viewport_dir, current_rows, page_key)
        signature = json.dumps([(row["resource_id"], row["text"], row["bounds"]) for row in current_rows], ensure_ascii=False)
        if signature in seen_signatures:
            if viewport > 0:
                break
        seen_signatures.add(signature)
        variants.append(
            {
                "viewport": viewport,
                "package": info["package"],
                "controls_exported": len(export_manifest),
                "page_dir": str((session_dir / page_key) if viewport == 0 else viewport_dir),
            }
        )
        if viewport < spec.max_scrolls:
            scroll_once()
    return variants


def navigate_to_page(spec: PageSpec, display_id: str, session_dir: Path, root_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if spec.page_key in {"vehicle_common", "vehicle_door_lock"}:
        return navigate_vehicle_subpage(spec, display_id, session_dir, root_rows)
    if spec.page_key == "vehicle_root":
        return root_rows, classify_rows(root_rows)
    if spec.parent_key is None:
        raise RuntimeError(f"Page {spec.page_key} has no parent navigation")
    parent_spec = PAGE_SPECS[spec.parent_key]
    parent_rows, _ = navigate_to_page(parent_spec, display_id, session_dir, root_rows)
    target = find_best_match(parent_rows, spec.selectors)
    if not target and spec.parent_key == "vehicle_root":
        target = search_in_left_menu(spec.selectors, display_id, session_dir / "_menu_search" / spec.page_key)
    if not target:
        raise RuntimeError(f"Unable to find target for page {spec.page_key}")
    tap(target["center_x"], target["center_y"])
    time.sleep(WAIT_AFTER_TAP)
    page_dir = session_dir / spec.page_key
    rows, info = capture_page(page_dir, display_id)
    if info["package"] != VEHICLE_PACKAGE:
        raise RuntimeError(f"Page {spec.page_key} drifted outside vehicle settings: {info['package']}")
    if not is_expected_page(rows, spec):
        raise RuntimeError(f"Page {spec.page_key} did not satisfy expected anchors")
    return rows, info


def navigate_vehicle_subpage(
    spec: PageSpec,
    display_id: str,
    session_dir: Path,
    root_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    vehicle_entry = find_best_match(
        root_rows,
        (
            Selector(resource_id="com.autolink.vehicle:id/vehicle"),
            Selector(text="车辆"),
        ),
    )
    if not vehicle_entry:
        vehicle_entry = search_in_left_menu(
            (
                Selector(resource_id="com.autolink.vehicle:id/vehicle"),
                Selector(text="车辆"),
            ),
            display_id,
            session_dir / "_menu_search" / "vehicle_entry",
        )
    if not vehicle_entry:
        raise RuntimeError("Unable to find target for page vehicle_root_vehicle_entry")

    tap(vehicle_entry["center_x"], vehicle_entry["center_y"])
    time.sleep(WAIT_AFTER_TAP)
    vehicle_dir = session_dir / "_vehicle_section" / spec.page_key
    vehicle_rows, vehicle_info = capture_page(vehicle_dir, display_id)
    if vehicle_info["package"] != VEHICLE_PACKAGE:
        raise RuntimeError(f"Vehicle page drifted outside expected package: {vehicle_info['package']}")

    if spec.page_key == "vehicle_common":
        if not is_expected_page(vehicle_rows, spec):
            raise RuntimeError("Vehicle common page did not satisfy expected anchors")
        page_dir = session_dir / spec.page_key
        rows, info = capture_page(page_dir, display_id)
        return rows, info

    tab_target = find_best_match(vehicle_rows, spec.selectors)
    if not tab_target:
        raise RuntimeError(f"Unable to find target for page {spec.page_key}")
    tap(tab_target["center_x"], tab_target["center_y"])
    time.sleep(WAIT_AFTER_TAP)
    page_dir = session_dir / spec.page_key
    rows, info = capture_page(page_dir, display_id)
    if info["package"] != VEHICLE_PACKAGE:
        raise RuntimeError(f"Page {spec.page_key} drifted outside vehicle settings: {info['package']}")
    if not is_expected_page(rows, spec):
        raise RuntimeError(f"Page {spec.page_key} did not satisfy expected anchors")
    return rows, info


def run_capture(page_keys: list[str], output_root: Path, display_id: str) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    session_dir = output_root / f"vehicle_settings_capture_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    root_rows, root_info = ensure_vehicle_root(display_id, session_dir)
    root_export = export_controls(session_dir / "vehicle_root", root_rows, "vehicle_root")
    manifest: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_dir": str(session_dir),
        "root_info": root_info,
        "pages": [
            {
                "page_key": "vehicle_root",
                "controls_exported": len(root_export),
                "variants": [{"viewport": 0, "package": root_info["package"], "controls_exported": len(root_export)}],
            }
        ],
        "errors": [],
    }

    for page_key in page_keys:
        if page_key == "vehicle_root":
            continue
        spec = PAGE_SPECS[page_key]
        try:
            root_rows, _ = ensure_vehicle_root(display_id, session_dir / "_root_refresh" / page_key)
            rows, info = navigate_to_page(spec, display_id, session_dir, root_rows)
            variants = capture_page_variants(page_key, rows, display_id, session_dir)
            export_count = variants[0]["controls_exported"] if variants else 0
            if not variants:
                variants = [{"viewport": 0, "package": info["package"], "controls_exported": export_count}]
            manifest["pages"].append(
                {
                    "page_key": page_key,
                    "page_name": PAGE_INDEX.get(page_key, {}).get("page_name", ""),
                    "controls_exported": export_count,
                    "variants": variants,
                }
            )
        except Exception as exc:  # noqa: BLE001
            manifest["errors"].append({"page_key": page_key, "error": str(exc)})
    (session_dir / "_meta").mkdir(exist_ok=True)
    (session_dir / "_meta" / "crawl_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture vehicle settings controls with page-tree navigation.")
    parser.add_argument("--output-root", required=True, help="Directory used to store capture output.")
    parser.add_argument("--display-id", required=True, help="Display id used by adb screencap -d.")
    parser.add_argument("--serial", help="ADB serial.")
    parser.add_argument(
        "--pages",
        nargs="*",
        default=DEFAULT_PAGE_ORDER,
        help="Page keys to capture. Defaults to all configured pages.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global ADB_SERIAL
    ADB_SERIAL = args.serial
    output_dir = run_capture(args.pages, Path(args.output_root), args.display_id)
    print(json.dumps({"output_dir": str(output_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
