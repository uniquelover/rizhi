#!/usr/bin/env python3
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "out" / "custom-scene-analysis"


HYBRID_PAGE_ALLOWLIST = {
    "推荐场景详情页",
    "新建场景页面",
    "非运行中场景编辑页",
    "我的场景页面",
    "自定义场景APP",
    "条件列表页",
    "动作列表页",
    "自定义场景首页",
}


def task_type(row):
    strategy = row["resource_strategy"]
    ui_type = row["ui_type"]
    if strategy == "template_first":
        if ui_type in {"button", "icon", "tab", "control"}:
            return "模板小图"
        if ui_type in {"dialog", "card"}:
            return "模板主体图"
        return "模板图"
    return "页面锚点图+标题OCR"


def capture_hint(row):
    ui_type = row["ui_type"]
    name = row["normalized_name"]
    if ui_type == "button":
        return "进入目标页面后截控件紧邻区域，保留按钮完整边界"
    if ui_type == "icon":
        return "截单个图标及少量安全边距，避免带入相邻文字"
    if ui_type == "tab":
        return "优先截选中态，必要时补未选中态"
    if ui_type == "dialog":
        return "截弹窗主体，标题和主要按钮都保留"
    if ui_type == "card":
        return "截卡片主体，保留标题和识别性图案"
    if ui_type == "page":
        return "截页面稳定锚点区域，同时记录页面标题OCR区域"
    if ui_type == "app":
        return "截应用首页稳定锚点，优先标题栏或首页主视觉"
    if ui_type == "state":
        return "截能体现状态差异的局部区域，必要时补OCR标题"
    if name in {"取消", "保存", "确定", "确认", "删除"}:
        return "优先在自定义场景上下文里截取，避免与系统通用按钮混淆"
    return "截取稳定可复用区域，避免带入动态内容"


def main():
    src = BASE / "ui_control_top50_classified.csv"
    with src.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    tasks = []
    priority = 0
    for row in rows:
        strategy = row["resource_strategy"]
        include = False
        batch = ""
        if strategy == "template_first":
            include = True
            batch = "template_first"
        elif strategy == "hybrid" and row["normalized_name"] in HYBRID_PAGE_ALLOWLIST:
            include = True
            batch = "hybrid_anchor"

        if not include:
            continue

        priority += 1
        tasks.append(
            {
                "priority": priority,
                "batch": batch,
                "normalized_name": row["normalized_name"],
                "suggested_asset_name": row["suggested_asset_name"],
                "ui_type": row["ui_type"],
                "resource_strategy": strategy,
                "task_type": task_type(row),
                "occurrences": row["occurrences"],
                "case_count": row["case_count"],
                "sample_case_ids": row["sample_case_ids"],
                "sample_sentences": row["sample_sentences"],
                "capture_hint": capture_hint(row),
            }
        )

    out_csv = BASE / "ui_screenshot_tasklist.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "priority",
                "batch",
                "normalized_name",
                "suggested_asset_name",
                "ui_type",
                "resource_strategy",
                "task_type",
                "occurrences",
                "case_count",
                "sample_case_ids",
                "sample_sentences",
                "capture_hint",
            ],
        )
        writer.writeheader()
        writer.writerows(tasks)

    summary = {
        "task_count": len(tasks),
        "template_first_count": sum(1 for task in tasks if task["batch"] == "template_first"),
        "hybrid_anchor_count": sum(1 for task in tasks if task["batch"] == "hybrid_anchor"),
        "top_20": tasks[:20],
    }
    out_json = BASE / "ui_screenshot_tasklist_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "csv": str(out_csv),
                "json": str(out_json),
                "task_count": summary["task_count"],
                "template_first_count": summary["template_first_count"],
                "hybrid_anchor_count": summary["hybrid_anchor_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
