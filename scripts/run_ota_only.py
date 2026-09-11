import argparse
import os
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def configure_cli_adb():
    adb_path = os.getenv("RIZHI_CLI_ADB_PATH", "").strip() or r"D:\platform-tools\adb.exe"
    adb_dir = os.path.dirname(adb_path)
    os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
    from airtest.core.android.adb import ADB
    from airtest.core.android.n50_adb import N50_ADB
    ADB.get_adb_path = staticmethod(lambda: adb_path)
    N50_ADB.get_adb_path = staticmethod(lambda: adb_path)


configure_cli_adb()

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from log_tool.log_layout import LogPreprocessUI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run OTA upgrade only flow for Jenkins."
    )
    parser.add_argument(
        "--target-time",
        help="Optional HH:MM target time for upgrade start.",
    )
    parser.add_argument(
        "--release-source",
        choices=("dev", "release"),
        help="Override OTA release source for CLI runs.",
    )
    parser.add_argument(
        "--feishu-webhook",
        default=os.getenv("FEISHU_WEBHOOK_URL"),
        help="Feishu bot webhook url for CLI runs.",
    )
    parser.add_argument(
        "--show-ui",
        action="store_true",
        help="Show the main window while running.",
    )
    return parser


def shutdown_cli(app, ui):
    try:
        ui.close()
    except Exception:
        pass
    try:
        app.quit()
    except Exception:
        pass


def main() -> int:
    args = build_parser().parse_args()

    os.environ.setdefault("RIZHI_SKIP_AUTO_OCR", "1")
    if args.release_source:
        os.environ["RIZHI_CLI_RELEASE_SOURCE"] = args.release_source
    if args.feishu_webhook:
        os.environ["RIZHI_CLI_FEISHU_WEBHOOK"] = args.feishu_webhook
    app = QApplication(sys.argv)
    ui = LogPreprocessUI()
    exit_code = {"value": 0}

    def finish(success=True, error_text=""):
        if not success:
            exit_code["value"] = 1
            if error_text:
                print(error_text)
        shutdown_cli(app, ui)

    def run_ota_only():
        try:
            if args.target_time:
                ui._append_upgrade_log(f"升级任务将于 {args.target_time} 执行")
                while True:
                    now_str = time.strftime("%H:%M")
                    if now_str == args.target_time:
                        ui._append_upgrade_log("时间匹配成功，开始执行...")
                        break
                    time.sleep(1)

            ui.test_process.setText("正在执行升级脚本")
            ota_config = ui._get_ota_config()
            ota_run_started_at = time.time()
            force_real_ota = bool(args.release_source)
            ota_artifact_dir = None
            if ota_config["debug_use_existing_artifact"] and not force_real_ota:
                ui._append_upgrade_log("已开启 OTA 假联调，跳过真实升级脚本，直接复用现有 artifacts")
                ota_run_started_at = 0
                ui._check_ota_phase_results_or_raise(ota_run_started_at)
            else:
                ota_artifact_dir = ui._run_external_ota_upgrade(ota_run_started_at)

            ui.test_process.setText("等待升级结果文件")
            if ota_artifact_dir:
                ui._wait_for_ota_phase_results_or_raise(
                    ota_artifact_dir,
                    poll_interval_seconds=max(1, min(5, int(ota_config["poll_interval_seconds"]))),
                    max_attempts=max(12, int(ota_config["max_poll_attempts"]) * 12),
                )
            version_compare_path = ui._wait_for_ota_version_compare(
                ota_run_started_at,
                poll_interval_seconds=ota_config["poll_interval_seconds"],
                max_attempts=ota_config["max_poll_attempts"],
                artifact_dir=ota_artifact_dir,
            )
            compare_data = ui._read_ota_version_compare(version_compare_path)
            ui._notify_ota_result(compare_data, version_compare_path)
            finish(success=True)
        except Exception as exc:
            finish(success=False, error_text=str(exc))

    def start_workflow():
        threading.Thread(target=run_ota_only, daemon=True).start()

    if args.show_ui:
        ui.show()

    QTimer.singleShot(0, start_workflow)
    app.exec_()
    shutdown_cli(app, ui)
    return exit_code["value"]


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
