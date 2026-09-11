import argparse
from collections import Counter, defaultdict
import json
import mimetypes
import os
from pathlib import Path

import requests
from openpyxl import load_workbook
import yaml


BASE_URL = "https://open.feishu.cn/open-apis"
RESULT_COLUMN = "自动化测试结果"
LEVEL_COLUMN = "用例等级"
DEFAULT_IGNORE_BLOCK_KEYWORDS = ("用户中心", "自定义场景", "恢复出厂设置")
CONF_PATH = Path(__file__).resolve().parent.parent / "data" / "conf.yml"


def find_header_row(sheet, required_headers):
    for row_idx in range(1, min(sheet.max_row, 10) + 1):
        headers = list(next(sheet.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True)))
        if all(header in headers for header in required_headers):
            return row_idx, headers
    raise RuntimeError(f"Headers {required_headers} not found in workbook")


def find_result_header_row(sheet):
    for row_idx in range(1, min(sheet.max_row, 10) + 1):
        headers = list(next(sheet.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True)))
        if RESULT_COLUMN in headers:
            return row_idx, headers
    raise RuntimeError(f"Header {RESULT_COLUMN} not found in workbook")


def resolve_file_type(file_path):
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".doc", ".docx", ".txt", ".rtf"}:
        return "doc"
    if ext in {".xls", ".xlsx", ".csv"}:
        return "xls"
    if ext in {".ppt", ".pptx"}:
        return "ppt"
    if ext == ".mp4":
        return "mp4"
    if ext == ".opus":
        return "opus"
    return "stream"


def get_tenant_access_token(app_id, app_secret):
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant_access_token: {data}")
    return data["tenant_access_token"]


def load_ignore_block_keywords():
    try:
        with open(CONF_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        return DEFAULT_IGNORE_BLOCK_KEYWORDS

    share_config = config.get("share", {})
    feishu_report = share_config.get("feishu_report", {})
    keywords = feishu_report.get("ignore_block_modules")
    if not keywords:
        return DEFAULT_IGNORE_BLOCK_KEYWORDS
    return tuple(str(item).strip() for item in keywords if str(item).strip())


def load_ignore_block_case_ids():
    try:
        with open(CONF_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        return set()

    share_config = config.get("share", {})
    feishu_report = share_config.get("feishu_report", {})
    case_ids = feishu_report.get("ignore_block_case_ids") or []
    normalized = set()
    for item in case_ids:
        text = str(item).strip()
        if text:
            normalized.add(text)
    return normalized


def normalize_result(result_text):
    text = str(result_text).strip().lower()
    if text in {"pass", "fail", "block"}:
        return text
    if not text:
        return ""
    return "other"


def should_ignore_block(row_values, excel_row_idx):
    ignore_keywords = load_ignore_block_keywords()
    ignore_case_ids = load_ignore_block_case_ids()
    if str(excel_row_idx) in ignore_case_ids:
        return True
    searchable = " ".join("" if value is None else str(value) for value in row_values[:7])
    return any(keyword in searchable for keyword in ignore_keywords)


def summarize_xlsx_result(file_path):
    workbook = load_workbook(file_path, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    try:
        header_row, headers = find_header_row(sheet, [RESULT_COLUMN, LEVEL_COLUMN])
        has_level = True
    except RuntimeError:
        header_row, headers = find_result_header_row(sheet)
        has_level = False

    result_idx = headers.index(RESULT_COLUMN)
    level_idx = headers.index(LEVEL_COLUMN) if has_level else None

    overall = Counter()
    level_counter = defaultdict(Counter)
    effective = Counter()
    effective_level_counter = defaultdict(Counter)

    for excel_row_idx, row in enumerate(
        sheet.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        result_value = row[result_idx] if len(row) > result_idx else None
        if result_value is None:
            continue

        normalized_result = normalize_result(result_value)
        if not normalized_result:
            continue

        level_text = None
        if has_level:
            level_value = row[level_idx] if len(row) > level_idx else None
            level_text = str(level_value).strip().upper() if level_value is not None else ""
            if not level_text:
                level_text = "UNKNOWN"

        overall[normalized_result] += 1
        if level_text is not None:
            level_counter[level_text][normalized_result] += 1

        if normalized_result == "block" and should_ignore_block(row, excel_row_idx):
            continue

        effective[normalized_result] += 1
        if level_text is not None:
            effective_level_counter[level_text][normalized_result] += 1

    return {
        "pass": overall.get("pass", 0),
        "fail": overall.get("fail", 0),
        "block": overall.get("block", 0),
        "other": overall.get("other", 0),
        "total": sum(overall.values()),
        "has_level": has_level,
        "level_counter": level_counter,
        "effective": effective,
        "effective_level_counter": effective_level_counter,
    }


def upload_file(token, file_path):
    url = f"{BASE_URL}/im/v1/files"
    file_name = os.path.basename(file_path)
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    file_type = resolve_file_type(file_path)

    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            data={"file_type": file_type, "file_name": file_name},
            files={"file": (file_name, f, mime_type)},
            timeout=60,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"File upload failed with HTTP {resp.status_code}:\n{resp.text}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"File upload failed: {data}")
    return data["data"]["file_key"]


def send_message(token, chat_id, msg_type, content):
    url = f"{BASE_URL}/im/v1/messages?receive_id_type=chat_id"
    payload = {
        "receive_id": chat_id,
        "msg_type": msg_type,
        "content": json.dumps(content, ensure_ascii=False),
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Message send failed with HTTP {resp.status_code}:\n{resp.text}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Message send failed: {data}")
    return data


def send_text_message(token, chat_id, text):
    return send_message(token, chat_id, "text", {"text": text})


def send_file_message(token, chat_id, file_key):
    return send_message(token, chat_id, "file", {"file_key": file_key})


def send_webhook_text(webhook_url, text):
    payload = {"msg_type": "text", "content": {"text": text}}
    resp = requests.post(webhook_url, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("StatusCode") not in (0, None):
        raise RuntimeError(f"Webhook send failed: {data}")
    return data


def build_summary_text(file_path, summary):
    if not summary.get("has_level", False):
        parts = [
            file_path.stem,
            "结论: 报告已生成",
            "原因: 当前报告不包含用例等级列，无法计算 P0/P1/P2 结论",
            "P0: N/A",
            "P1: N/A",
            "P2: N/A",
            f"Total: pass {summary['pass']}, fail {summary['fail']}, block {summary['block']}",
        ]
        return "\n".join(parts)

    level_counter = summary.get("level_counter", {})
    effective = summary.get("effective", Counter())
    effective_level_counter = summary.get("effective_level_counter", {})
    p0 = level_counter.get("P0", Counter())
    p1 = level_counter.get("P1", Counter())
    p2 = level_counter.get("P2", Counter())
    effective_p1 = effective_level_counter.get("P1", Counter())

    p1_total = effective_p1.get("pass", 0) + effective_p1.get("fail", 0) + effective_p1.get("block", 0)
    p1_pass_rate = (effective_p1.get("pass", 0) / p1_total) if p1_total else 0.0

    if p0.get("fail", 0) > 0:
        conclusion = "不通过"
        reason = "P0 存在失败"
    elif effective.get("block", 0) > 0:
        conclusion = "不通过"
        reason = "存在阻断或严重缺陷"
    elif p0.get("pass", 0) == 0:
        conclusion = "不通过"
        reason = "P0 未执行或未通过"
    elif p1_total == 0:
        conclusion = "不通过"
        reason = "关键模块未执行"
    elif p1_pass_rate >= 0.95:
        conclusion = "通过"
        reason = f"P1 通过率 {p1_pass_rate:.0%}，满足阈值"
    else:
        conclusion = "有条件通过"
        reason = f"P1 通过率 {p1_pass_rate:.0%}，存在少量失败"

    parts = [
        file_path.stem,
        f"结论: {conclusion}",
        f"原因: {reason}",
        "说明: 用户中心、自定义场景、恢复出厂设置的 block 不参与结论判定",
        f"P0: pass {p0.get('pass', 0)}, fail {p0.get('fail', 0)}, block {p0.get('block', 0)}",
        f"P1: pass {p1.get('pass', 0)}, fail {p1.get('fail', 0)}, block {p1.get('block', 0)}",
        f"P2: pass {p2.get('pass', 0)}, fail {p2.get('fail', 0)}, block {p2.get('block', 0)}",
        f"Total: pass {summary['pass']}, fail {summary['fail']}, block {summary['block']}",
    ]
    return "\n".join(parts)


def parse_args():
    parser = argparse.ArgumentParser(description="Upload a local report file to a Feishu chat.")
    parser.add_argument("--app-id", default=os.getenv("FEISHU_APP_ID"), help="Feishu app id")
    parser.add_argument("--app-secret", default=os.getenv("FEISHU_APP_SECRET"), help="Feishu app secret")
    parser.add_argument("--chat-id", default=os.getenv("FEISHU_CHAT_ID"), help="Target Feishu chat_id")
    parser.add_argument("--file", default=os.getenv("FEISHU_TEST_FILE"), help="Local file path to upload")
    return parser.parse_args()


def send_report(app_id, app_secret, chat_id, file_path):
    file_path = Path(file_path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if file_path.suffix.lower() != ".xlsx":
        raise RuntimeError("Only xlsx reports are supported for pass/fail summary")

    token = get_tenant_access_token(app_id, app_secret)
    summary = summarize_xlsx_result(file_path)
    summary_text = build_summary_text(file_path, summary)
    send_text_message(token, chat_id, summary_text)
    file_key = upload_file(token, str(file_path))
    return send_file_message(token, chat_id, file_key)


def send_report_via_webhook(webhook_url, file_path):
    file_path = Path(file_path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if file_path.suffix.lower() != ".xlsx":
        raise RuntimeError("Only xlsx reports are supported for pass/fail summary")

    summary = summarize_xlsx_result(file_path)
    summary_text = build_summary_text(file_path, summary)
    return send_webhook_text(webhook_url, summary_text)


def main():
    args = parse_args()
    missing = []
    if not args.app_id:
        missing.append("app_id / FEISHU_APP_ID")
    if not args.app_secret:
        missing.append("app_secret / FEISHU_APP_SECRET")
    if not args.chat_id:
        missing.append("chat_id / FEISHU_CHAT_ID")
    if not args.file:
        missing.append("file / FEISHU_TEST_FILE")
    if missing:
        raise SystemExit(f"Missing arguments: {', '.join(missing)}")

    print(f"[1/4] Getting token: app_id={args.app_id}")
    result = send_report(
        app_id=args.app_id,
        app_secret=args.app_secret,
        chat_id=args.chat_id,
        file_path=args.file,
    )
    print("[OK] File message sent")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
