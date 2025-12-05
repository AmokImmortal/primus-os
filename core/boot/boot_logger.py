"""
PRIMUS OS — Boot Logger (Milestone 2)
Very small logger used only during boot.
Writes to System/logs/boot.log
"""
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "boot.log"


def log(message: str):
    """Append timestamped log entry to boot.log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as exc:  # pragma: no cover - safety logging only
        print(f"[boot_logger] Failed to write log: {exc}")


def log_startup():
    log("=== PRIMUS OS Boot Sequence Initiated ===")


def log_shutdown():
    log("=== PRIMUS OS Boot Sequence End ===")


if __name__ == "__main__":
    log("boot_logger test entry")
