import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.test_feishu_send import send_report, send_report_via_webhook


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send the generated xlsx report to Feishu."
    )
    parser.add_argument(
        "--report",
        default=os.getenv("FEISHU_TEST_FILE"),
        help="Report xlsx path. Defaults to FEISHU_TEST_FILE.",
    )
    parser.add_argument(
        "--app-id",
        default=os.getenv("FEISHU_APP_ID"),
        help="Feishu app id",
    )
    parser.add_argument(
        "--app-secret",
        default=os.getenv("FEISHU_APP_SECRET"),
        help="Feishu app secret",
    )
    parser.add_argument(
        "--chat-id",
        default=os.getenv("FEISHU_CHAT_ID"),
        help="Feishu chat id",
    )
    parser.add_argument(
        "--webhook",
        default=os.getenv("FEISHU_WEBHOOK_URL"),
        help="Feishu bot webhook url. When provided, send summary text via webhook instead of app_id/app_secret/chat_id.",
    )
    return parser.parse_args()


def resolve_report_path(raw_path):
    if raw_path:
        return Path(raw_path).expanduser().resolve()

    generated_dir = Path(PROJECT_ROOT) / "test_report" / "T1V" / "generated"
    if generated_dir.exists():
        latest_xlsx = sorted(
            generated_dir.glob("*.xlsx"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if latest_xlsx:
            return latest_xlsx[0].resolve()

    latest_report_file = Path(PROJECT_ROOT) / "out" / "latest_report.txt"
    if not latest_report_file.exists():
        raise FileNotFoundError(f"latest_report.txt not found: {latest_report_file}")

    report_path = latest_report_file.read_text(encoding="utf-8").strip()
    if not report_path:
        raise RuntimeError(f"latest_report.txt is empty: {latest_report_file}")

    return Path(report_path).expanduser().resolve()


def main():
    args = parse_args()

    report_path = resolve_report_path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(report_path)

    if args.webhook:
        print(f"Sending Feishu summary via webhook: {report_path}")
        send_report_via_webhook(
            webhook_url=args.webhook,
            file_path=str(report_path),
        )
        print("Feishu webhook summary sent successfully")
        return

    missing = []
    if not args.app_id:
        missing.append("FEISHU_APP_ID")
    if not args.app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not args.chat_id:
        missing.append("FEISHU_CHAT_ID")
    if missing:
        raise SystemExit(f"Missing environment or arguments: {', '.join(missing)}")

    print(f"Sending Feishu report: {report_path}")
    send_report(
        app_id=args.app_id,
        app_secret=args.app_secret,
        chat_id=args.chat_id,
        file_path=str(report_path),
    )
    print("Feishu report sent successfully")


if __name__ == "__main__":
    main()
