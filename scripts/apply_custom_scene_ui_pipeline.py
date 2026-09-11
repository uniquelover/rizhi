#!/usr/bin/env python3
import csv
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "custom_scene_ui_pipeline_config.py"
OUT_DIR = ROOT / "out" / "custom-scene-analysis"


def load_config():
    spec = importlib.util.spec_from_file_location("custom_scene_ui_pipeline_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PIPELINE


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def sync_labels(config):
    label_root = ROOT / config["label_root"]
    rows = []
    for item in config["label_mappings"]:
        src = ROOT / item["source_image"]
        dst = label_root / f'{item["ascii_label"]}.png'
        ensure_parent(dst)
        if not src.exists():
            raise FileNotFoundError(f"missing source image: {src}")
        shutil.copyfile(src, dst)
        rows.append(
            {
                "control_name_cn": item["control_name_cn"],
                "page": item["page"],
                "source_image": item["source_image"],
                "ascii_label": item["ascii_label"],
                "target_image": str(dst.relative_to(ROOT)).replace("\\", "/"),
                "match_mode": item["match_mode"],
                "notes": item.get("notes", ""),
            }
        )
    return rows


def write_label_manifest(rows):
    path = OUT_DIR / "custom_scene_ui_label_manifest.csv"
    ensure_parent(path)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "control_name_cn",
                "page",
                "source_image",
                "ascii_label",
                "target_image",
                "match_mode",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_scripts(config):
    script_root = ROOT / config["script_root"]
    rows = []
    for case in config["case_scripts"]:
        path = script_root / case["filename"]
        ensure_parent(path)
        content = "\n".join(case["steps"]) + "\n"
        path.write_text(content, encoding="utf-8")
        labels = []
        for line in case["steps"]:
            if line.startswith("touch: ") or line.startswith("check: "):
                label = line.split(": ", 1)[1].strip()
                if label != "Home1":
                    labels.append(label)
        rows.append(
            {
                "filename": case["filename"],
                "case_id": case["case_id"],
                "title": case["title"],
                "purpose": case["purpose"],
                "label_dependencies": ",".join(dict.fromkeys(labels)),
            }
        )
    return rows


def write_case_manifest(rows):
    path = OUT_DIR / "custom_scene_case_script_manifest.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["filename", "case_id", "title", "purpose", "label_dependencies"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def verify(config):
    label_root = ROOT / config["label_root"]
    fallback_root = ROOT / "press_android" / "label_pic"
    missing = []
    for case in config["case_scripts"]:
        for line in case["steps"]:
            if not (line.startswith("touch: ") or line.startswith("check: ")):
                continue
            label = line.split(": ", 1)[1].strip()
            if label == "Home1":
                continue
            in_module = (label_root / f"{label}.png").exists()
            in_fallback = (fallback_root / f"{label}.png").exists()
            if not in_module and not in_fallback:
                missing.append({"filename": case["filename"], "label": label})
    return missing


def main():
    config = load_config()
    label_rows = sync_labels(config)
    case_rows = write_scripts(config)
    label_manifest = write_label_manifest(label_rows)
    case_manifest = write_case_manifest(case_rows)
    missing = verify(config)
    summary = {
        "module": config["module"],
        "label_count": len(label_rows),
        "case_count": len(case_rows),
        "label_manifest": str(label_manifest.relative_to(ROOT)).replace("\\", "/"),
        "case_manifest": str(case_manifest.relative_to(ROOT)).replace("\\", "/"),
        "missing_dependencies": missing,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
