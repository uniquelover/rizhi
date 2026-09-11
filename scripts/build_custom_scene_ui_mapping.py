#!/usr/bin/env python3
import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "out" / "custom-scene-analysis"


def load_rows():
    analysis_path = BASE / "analysis.csv"
    with analysis_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    return header, rows


def ui_feasible_rows(rows):
    idx_reasons = 6
    exclude = {"voice", "multi_finger", "scan_login", "factory_reset", "layout_review"}
    result = []
    for row in rows:
        reasons = {item for item in row[idx_reasons].split(",") if item}
        if reasons & exclude:
            continue
        result.append(row)
    return result


PATTERNS = [
    (
        "点击控件",
        r"(?:点击|点按|长按|短按|轻触|选择|选中|勾选)([^\n，。；]+?(?:按钮|按键|图标|页签|Tab|tab|卡片|选项|控件|应用图标|应用))",
    ),
    (
        "进入页面",
        r"(?:进入|打开|跳转到|跳转至|切换到|返回到)([^\n，。；]+?(?:页面|界面|首页|APP|弹窗|页签|Tab|tab|页))",
    ),
    (
        "显示对象",
        r"(?:显示|弹出|出现)([^\n，。；]+?(?:页面|界面|首页|弹窗|页签|Tab|tab|按钮|图标|卡片|文案|提示|toast))",
    ),
    (
        "查看对象",
        r"(?:查看|观察)([^\n，。；]+?(?:状态|页面|界面|首页|文案|提示|toast|按钮|图标|卡片|页签))",
    ),
    ("文案提示", r"(?:toast提示|toast显示|提示|文案为|文案显示)([^\n；。]+)"),
    ("通用对象", r"(?:点击|进入|打开|跳转到|跳转至|显示|弹出|切换到)([^\n，。；]{2,20})"),
]

STOP_TERMS = {
    "系统正常启动",
    "系统正常运行",
    "场景正在执行动作",
    "恢复网络",
    "恢复网络后检查",
    "操作后观察场景",
    "来电",
    "电话",
    "场景状态",
    "无状态异常",
    "正常滑动",
    "数据",
    "正确性",
    "功能",
    "入口功能",
    "退出功能",
}

SUFFIX_TYPES = [
    ("按钮", "button"),
    ("按键", "button"),
    ("图标", "icon"),
    ("页签", "tab"),
    ("Tab", "tab"),
    ("tab", "tab"),
    ("卡片", "card"),
    ("弹窗", "dialog"),
    ("页面", "page"),
    ("界面", "page"),
    ("首页", "page"),
    ("APP", "app"),
    ("文案", "text"),
    ("提示", "text"),
    ("toast", "text"),
    ("应用", "app"),
]


def clean_text(text):
    text = text.strip().strip("\"“”‘’()（）[]【】:：,，.。；;")
    text = re.sub(r"^[-+0-9一二三四五六七八九十]+[\\.、]?", "", text).strip()
    text = text.replace("tab页", "页签").replace("Tab页", "页签")
    text = text.replace("tab", "页签").replace("Tab", "页签")
    text = re.sub(r"\s+", "", text)
    return text


def normalize_name(text):
    text = clean_text(text)
    replacements = {
        "去登录按键": "去登录按钮",
        "自定义场景应用图标": "自定义场景入口图标",
        "dock栏自定义场景应用图标": "dock栏自定义场景入口图标",
        "tab分页我的场景": "我的场景页签",
        "tab分页场景推荐": "场景推荐页签",
        "页签分页我的场景": "我的场景页签",
        "页签分页场景推荐": "场景推荐页签",
        "使用此模版创建”按钮": "使用此模版创建按钮",
        "“使用此模版创建”按钮": "使用此模版创建按钮",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.replace("tab分页", "").replace("tab", "").replace("Tab", "")
    text = text.replace("页签页签", "页签")
    text = text.replace("“", "").replace("”", "")
    text = re.sub(r"^底部dock栏将(.+?)加入$", r"\1", text)
    text = re.sub(r"^可以进行切换到(.+)$", r"\1", text)
    text = re.sub(r"^切换到(.+)$", r"\1", text)
    text = re.sub(r"^跳转到(.+)$", r"\1", text)
    return text.strip("，。；;")


def infer_type(name, group):
    for suffix, ui_type in SUFFIX_TYPES:
        if suffix in name:
            return ui_type
    defaults = {
        "点击控件": "control",
        "进入页面": "page",
        "显示对象": "state",
        "查看对象": "state",
        "文案提示": "text",
        "通用对象": "control",
    }
    return defaults.get(group, "control")


def infer_capture(ui_type, name):
    need_ocr = ui_type == "text" or ("toast" in name.lower()) or ("文案" in name)
    need_image = not need_ocr
    return need_image, need_ocr


def extract_records(rows):
    idx_case = 1
    idx_pre = 7
    idx_steps = 8
    idx_expect = 9

    records = []
    for row in rows:
        case_id = row[idx_case]
        fields = [
            ("前提条件", row[idx_pre]),
            ("操作步骤", row[idx_steps]),
            ("期望结果", row[idx_expect]),
        ]
        for field_name, text in fields:
            lines = [item.strip() for item in re.split(r"\n+", text) if item.strip()]
            for line in lines:
                for group, pattern in PATTERNS:
                    for match in re.finditer(pattern, line):
                        raw = clean_text(match.group(1))
                        if not raw:
                            continue
                        raw = re.split(r"观察|检查|是否|后", raw)[0].strip()
                        raw = clean_text(raw)
                        if len(raw) < 2 or raw in STOP_TERMS:
                            continue
                        if raw.startswith("自定义场景") and raw.endswith("功能"):
                            continue
                        normalized = normalize_name(raw)
                        if len(normalized) < 2:
                            continue
                        ui_type = infer_type(normalized, group)
                        need_image, need_ocr = infer_capture(ui_type, normalized)
                        records.append(
                            {
                                "case_id": case_id,
                                "source_field": field_name,
                                "group": group,
                                "raw_text": raw,
                                "normalized_name": normalized,
                                "ui_type": ui_type,
                                "need_image": "yes" if need_image else "no",
                                "need_ocr": "yes" if need_ocr else "no",
                                "source_sentence": line,
                            }
                        )

    seen = set()
    deduped = []
    for record in records:
        key = (
            record["case_id"],
            record["source_field"],
            record["normalized_name"],
            record["source_sentence"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_catalog(records):
    catalog = {}
    for record in records:
        name = record["normalized_name"]
        entry = catalog.setdefault(
            name,
            {
                "normalized_name": name,
                "ui_type": record["ui_type"],
                "need_image": record["need_image"],
                "need_ocr": record["need_ocr"],
                "occurrences": 0,
                "case_ids": set(),
                "raw_texts": Counter(),
                "source_fields": Counter(),
                "sample_sentences": [],
            },
        )
        entry["occurrences"] += 1
        entry["case_ids"].add(record["case_id"])
        entry["raw_texts"][record["raw_text"]] += 1
        entry["source_fields"][record["source_field"]] += 1
        if len(entry["sample_sentences"]) < 3 and record["source_sentence"] not in entry["sample_sentences"]:
            entry["sample_sentences"].append(record["source_sentence"])

    rows = []
    for name, entry in catalog.items():
        rows.append(
            {
                "normalized_name": name,
                "suggested_asset_name": f"自定义场景_{name}",
                "ui_type": entry["ui_type"],
                "need_image": entry["need_image"],
                "need_ocr": entry["need_ocr"],
                "occurrences": entry["occurrences"],
                "case_count": len(entry["case_ids"]),
                "top_raw_text": entry["raw_texts"].most_common(1)[0][0],
                "source_fields": ",".join(key for key, _ in entry["source_fields"].most_common()),
                "sample_case_ids": ",".join(sorted(entry["case_ids"])[:8]),
                "sample_sentences": " | ".join(entry["sample_sentences"]),
            }
        )
    rows.sort(key=lambda item: (-int(item["occurrences"]), item["normalized_name"]))
    return rows


def write_outputs(records, catalog_rows, case_count):
    detail_path = BASE / "ui_control_mapping_detail.csv"
    with detail_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "case_id",
                "source_field",
                "group",
                "raw_text",
                "normalized_name",
                "ui_type",
                "need_image",
                "need_ocr",
                "source_sentence",
            ],
        )
        writer.writeheader()
        writer.writerows(records)

    catalog_path = BASE / "ui_control_catalog.csv"
    with catalog_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "normalized_name",
                "suggested_asset_name",
                "ui_type",
                "need_image",
                "need_ocr",
                "occurrences",
                "case_count",
                "top_raw_text",
                "source_fields",
                "sample_case_ids",
                "sample_sentences",
            ],
        )
        writer.writeheader()
        writer.writerows(catalog_rows)

    summary_path = BASE / "ui_control_catalog_summary.json"
    summary = {
        "ui_feasible_case_count": case_count,
        "mapping_detail_count": len(records),
        "unique_control_count": len(catalog_rows),
        "top_controls": catalog_rows[:20],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return detail_path, catalog_path, summary_path


def main():
    _, rows = load_rows()
    filtered_rows = ui_feasible_rows(rows)
    records = extract_records(filtered_rows)
    catalog_rows = build_catalog(records)
    detail_path, catalog_path, summary_path = write_outputs(records, catalog_rows, len(filtered_rows))
    print(
        json.dumps(
            {
                "ui_feasible_case_count": len(filtered_rows),
                "mapping_detail_count": len(records),
                "unique_control_count": len(catalog_rows),
                "detail_path": str(detail_path),
                "catalog_path": str(catalog_path),
                "summary_path": str(summary_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
