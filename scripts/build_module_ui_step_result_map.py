#!/usr/bin/env python3
import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "custom_scene_ui_pipeline_config.py"
OUT_DIR = ROOT / "out" / "custom-scene-analysis"


PUBLIC_LABELS = {
    "Home1": {
        "control_name_cn": "HOME",
        "page": "公共控件",
        "image_path": "press_android/label_pic/T1V/Home1.png",
        "source_image": "press_android/label_pic/T1V/Home1.png",
        "match_mode": "image",
        "notes": "系统 HOME 键",
    },
    "custom_scene_app_entry": {
        "control_name_cn": "自定义场景入口",
        "page": "公共控件",
        "image_path": "press_android/label_pic/custom_scene_app_entry.png",
        "source_image": "press_android/label_pic/custom_scene_app_entry.png",
        "match_mode": "image",
        "notes": "进入自定义场景的公共入口",
    }
}


def load_pipeline():
    spec = importlib.util.spec_from_file_location("custom_scene_cfg", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PIPELINE


def build_label_index(pipeline):
    label_index = {}
    for item in pipeline["label_mappings"]:
        label_index[item["ascii_label"]] = {
            "control_name_cn": item["control_name_cn"],
            "page": item["page"],
            "source_image": item["source_image"],
            "image_path": f'{pipeline["label_root"]}/{item["ascii_label"]}.png',
            "match_mode": item["match_mode"],
            "notes": item.get("notes", ""),
        }
    label_index.update(PUBLIC_LABELS)
    return label_index


def parse_steps(case):
    rows = []
    step_no = 0
    for line in case["steps"]:
        if not (line.startswith("touch: ") or line.startswith("check: ")):
            continue
        action, label = line.split(": ", 1)
        step_no += 1
        rows.append(
            {
                "step_no": step_no,
                "action_type": action,
                "label": label.strip(),
            }
        )
    return rows


def build_rows(pipeline):
    label_index = build_label_index(pipeline)
    rows = []
    for case in pipeline["case_scripts"]:
        for item in parse_steps(case):
            label = item["label"]
            meta = label_index.get(
                label,
                {
                    "control_name_cn": "",
                    "page": "",
                    "source_image": "",
                    "image_path": "",
                    "match_mode": "",
                    "notes": "missing mapping",
                },
            )
            rows.append(
                {
                    "module": pipeline["module"],
                    "case_id": case["case_id"],
                    "script_file": case["filename"],
                    "case_title": case["title"],
                    "case_purpose": case["purpose"],
                    "step_no": item["step_no"],
                    "action_type": item["action_type"],
                    "ascii_label": label,
                    "control_name_cn": meta["control_name_cn"],
                    "page": meta["page"],
                    "image_path": meta["image_path"],
                    "source_image": meta["source_image"],
                    "match_mode": meta["match_mode"],
                    "notes": meta["notes"],
                }
            )
    return rows


def write_csv(rows):
    out_csv = OUT_DIR / "custom_scene_ui_step_result_map.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "module",
                "case_id",
                "script_file",
                "case_title",
                "case_purpose",
                "step_no",
                "action_type",
                "ascii_label",
                "control_name_cn",
                "page",
                "image_path",
                "source_image",
                "match_mode",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return out_csv


def write_md(rows):
    out_md = OUT_DIR / "custom_scene_ui_step_result_map.md"
    lines = [
        "# 自定义场景 UI 步骤/结果映射表",
        "",
        "说明：",
        "- `action_type=touch` 表示步骤里需要点击的 UI 图。",
        "- `action_type=check` 表示结果里需要断言的 UI 图。",
        "- `Home1` 属于公共控件，图片对应 `press_android/label_pic/T1V/Home1.png`。",
        "",
        "| 用例ID | 脚本 | 序号 | 动作 | 标签名 | 中文控件名 | 页面 | 图片路径 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['script_file']} | {row['step_no']} | {row['action_type']} | "
            f"{row['ascii_label']} | {row['control_name_cn']} | {row['page']} | {row['image_path']} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


def main():
    pipeline = load_pipeline()
    rows = build_rows(pipeline)
    out_csv = write_csv(rows)
    out_md = write_md(rows)
    print(f"csv={out_csv.relative_to(ROOT).as_posix()}")
    print(f"md={out_md.relative_to(ROOT).as_posix()}")
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
