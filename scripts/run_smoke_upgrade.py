import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

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

from PyQt5.QtWidgets import QApplication

from log_tool.log_layout import LogPreprocessUI

OCR_SERVER_EXE = Path(PROJECT_ROOT) / "ocr_server" / "ocr_server.exe"


def wait_for_ocr_ready(host="127.0.0.1", port=8123, timeout_seconds=30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def ensure_ocr_ready(ui, timeout_seconds=30):
    print("CLI: checking OCR port 127.0.0.1:8123")
    if wait_for_ocr_ready(timeout_seconds=2):
        print("CLI: OCR port already ready, reuse existing service")
        ui._append_upgrade_log("CLI upgrade+smoke mode: OCR service already running")
        return

    if not OCR_SERVER_EXE.exists():
        raise FileNotFoundError(f"OCR executable not found: {OCR_SERVER_EXE}")

    print(f"CLI: OCR port not ready, starting OCR service: {OCR_SERVER_EXE}")
    ui._append_upgrade_log(f"CLI upgrade+smoke mode: starting OCR service: {OCR_SERVER_EXE}")
    ui.process = subprocess.Popen(
        [str(OCR_SERVER_EXE)],
        cwd=str(OCR_SERVER_EXE.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    ui._append_upgrade_log("CLI upgrade+smoke mode: OCR start requested")

    def _drain_ocr_output():
        try:
            for line in iter(ui.process.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    print(f"OCR: {line}")
        except Exception as exc:
            print(f"OCR output watcher failed: {exc}")

    import threading

    threading.Thread(target=_drain_ocr_output, daemon=True).start()

    if not wait_for_ocr_ready(timeout_seconds=timeout_seconds):
        raise RuntimeError(f"OCR service did not become ready within {timeout_seconds} seconds")

    print("CLI: OCR service is ready")
    ui._append_upgrade_log("CLI upgrade+smoke mode: OCR service is ready")


def restore_ethernet_adb():
    restore_bat = Path(PROJECT_ROOT) / "restore_adb_network.bat"
    if not restore_bat.exists():
        raise FileNotFoundError(f"ADB restore script not found: {restore_bat}")

    print(f"CLI: restoring ethernet adb via {restore_bat}")
    result = subprocess.run(
        ["cmd", "/c", str(restore_bat)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.returncode != 0:
        raise RuntimeError(f"Failed to restore ethernet adb: {result.returncode}")

    ethernet_serial = os.getenv("RIZHI_ETHERNET_ADB_SERIAL", "").strip()
    ethernet_ip = os.getenv("RIZHI_ETHERNET_ADB_IP", "").strip()
    if ethernet_serial:
        os.environ["RIZHI_ADB_SERIAL"] = ethernet_serial
        os.environ["RIZHI_ADB_IP"] = ethernet_serial.rsplit(":", 1)[0]
    elif ethernet_ip:
        os.environ["RIZHI_ADB_IP"] = ethernet_ip
        os.environ["RIZHI_ADB_SERIAL"] = f"{ethernet_ip}:5555"
    else:
        raise RuntimeError(
            "Ethernet adb restore completed without "
            "RIZHI_ETHERNET_ADB_SERIAL or RIZHI_ETHERNET_ADB_IP"
        )

    print(
        "CLI: ethernet adb restored, "
        f"serial={os.environ['RIZHI_ADB_SERIAL']} "
        f"ip={os.environ['RIZHI_ADB_IP']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OTA upgrade plus smoke test flow for Jenkins.")
    parser.add_argument("--target-time", help="Optional HH:MM target time for upgrade start.")
    parser.add_argument("--release-source", choices=("dev", "release"), help="Override OTA release source for CLI runs.")
    parser.add_argument("--feishu-webhook", default=os.getenv("FEISHU_WEBHOOK_URL"), help="Feishu bot webhook url for CLI runs.")
    return parser


def shutdown_cli(app, ui):
    try:
        if getattr(ui, "process", None) and ui.process.poll() is None:
            ui.process.terminate()
    except Exception:
        pass
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
    os.environ["RIZHI_PRECHECK_PAUSE"] = "0"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if args.release_source:
        os.environ["RIZHI_CLI_RELEASE_SOURCE"] = args.release_source
    if args.feishu_webhook:
        os.environ["RIZHI_CLI_FEISHU_WEBHOOK"] = args.feishu_webhook

    exit_code = 0
    app = None
    ui = None
    try:
        # Make every new Jenkins run start from the ethernet target.
        restore_ethernet_adb()
        print(f"CLI adb env: serial={os.getenv('RIZHI_ADB_SERIAL', '').strip()} ip={os.getenv('RIZHI_ADB_IP', '').strip()}")
        app = QApplication(sys.argv)
        ui = LogPreprocessUI()
        ensure_ocr_ready(ui)

        if args.target_time:
            print(f"CLI: waiting for target time {args.target_time}")
            while True:
                if time.strftime("%H:%M") == args.target_time:
                    print("CLI: target time matched")
                    break
                time.sleep(1)

        ota_artifact_dir = None
        ota_config = ui._get_ota_config()
        ota_run_started_at = time.time()

        if ota_config["debug_use_existing_artifact"]:
            print("CLI: reusing existing OTA artifacts")
            ui._check_ota_phase_results_or_raise(0)
            ota_run_started_at = 0
        else:
            print("CLI: starting external OTA runner")
            ota_artifact_dir = ui._run_external_ota_upgrade(ota_run_started_at)

        print("CLI: waiting for OTA result file")
        version_compare_path = ui._wait_for_ota_version_compare(
            ota_run_started_at,
            poll_interval_seconds=ota_config["poll_interval_seconds"],
            max_attempts=ota_config["max_poll_attempts"],
            artifact_dir=ota_artifact_dir,
        )
        compare_data = ui._read_ota_version_compare(version_compare_path)
        ui._notify_ota_result(compare_data, version_compare_path)

        ui._run_android_smoke_prep()
        ui._execute_smoke_and_report(run_smoke_prep=False)
    except Exception as exc:
        exit_code = 1
        print(exc)
        import traceback
        traceback.print_exc()
    finally:
        try:
            restore_ethernet_adb()
        except Exception as restore_exc:
            print(f"CLI: ethernet adb restore failed: {restore_exc}")
            import traceback
            traceback.print_exc()
            if exit_code == 0:
                exit_code = 1
        shutdown_cli(app, ui)
        from video.demo import Testvalues

        Testvalues.test_datas = {}
        Testvalues.diff_datas = {}
        Testvalues.position_args = ""
        Testvalues.total_cases = 0
        Testvalues.test_types = ""

    return exit_code


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
