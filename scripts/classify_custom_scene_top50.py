#!/usr/bin/env python3
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "out" / "custom-scene-analysis"


OCR_KEYWORDS = {
    "toast",
    "提示",
    "信息",
    "结果",
    "文案",
    "请输入",
    "运行中，请终止",
}

TEMPLATE_TYPES = {"button", "icon", "tab", "card", "dialog", "control"}
HYBRID_TYPES = {"page", "app", "state"}


def classify(row):
    name = row["normalized_name"]
    ui_type = row["ui_type"]
    name_lower = name.lower()

    has_ocr_signal = any(keyword in name_lower or keyword in name for keyword in OCR_KEYWORDS)

    if has_ocr_signal and ui_type == "text":
        return "ocr_first", "文案类，优先保留运行时截图 + OCR 区域"

    if ui_type in TEMPLATE_TYPES:
        if has_ocr_signal:
            return "hybrid", "控件带文字属性，建议模板图和 OCR 都保留"
        return "template_first", "可视结构稳定，优先补模板图"

    if ui_type in HYBRID_TYPES:
        if has_ocr_signal:
            return "hybrid", "页面/状态既可做锚点图，也适合保留 OCR 标题校验"
        return "hybrid", "页面/状态建议保留锚点图，同时可补标题 OCR"

    if ui_type == "text":
        return "ocr_first", "文本为主，优先 OCR"

    return "hybrid", "默认按混合资源处理"


def main():
    src = BASE / "ui_control_top50.csv"
    with src.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    classified = []
    for row in rows:
        strategy, note = classify(row)
        item = dict(row)
        item["resource_strategy"] = strategy
        item["note"] = note
        classified.append(item)

    out_csv = BASE / "ui_control_top50_classified.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(classified[0].keys()),
        )
        writer.writeheader()
        writer.writerows(classified)

    grouped = {"template_first": [], "ocr_first": [], "hybrid": []}
    for item in classified:
        grouped[item["resource_strategy"]].append(item)

    for key in grouped:
        grouped[key].sort(key=lambda item: (-int(item["occurrences"]), item["normalized_name"]))

    summary = {
        "counts": {key: len(value) for key, value in grouped.items()},
        "template_first": grouped["template_first"],
        "ocr_first": grouped["ocr_first"],
        "hybrid": grouped["hybrid"],
    }

    out_json = BASE / "ui_control_top50_classified.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "csv": str(out_csv),
                "json": str(out_json),
                "counts": summary["counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
