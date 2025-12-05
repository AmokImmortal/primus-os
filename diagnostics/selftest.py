import json
import time
from datetime import datetime
from pathlib import Path

# ============================================================
#  PRIMUS SYSTEM SELF-TEST MODULE
#  Phase 2 — Core Path / File Existence & Integrity Check
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent  # /System
SYSTEM_ROOT = ROOT_DIR  # alias for clarity
PRIMUS_ROOT = ROOT_DIR.parent                     # repo root
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "selftest_latest.json"

REQUIRED_PATHS = [
    "core/",
    "rag/",
    "interfaces/",
    "diagnostics/",
    "captains_log_vault/",
    "checkpoints/",
    "configs/system_paths.json",
    "core/primus_runtime.py",
    "core/primus_bridge.py",
    "core/rag_manager.py",
    "interfaces/captains_log_interface.py",
    "core/captains_log_manager.py",
    "core/primus_cli.py",
]


def log(result: dict):
    """Write test results to a JSON log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)


def check_required_paths():
    """Verifies presence of required folders & files."""
    missing = []
    for rel in REQUIRED_PATHS:
        full = PRIMUS_ROOT / "System" / rel
        if not full.exists():
            missing.append(rel)
    return missing


def run_selftest():
    """Runs all core system diagnostics."""
    start = time.time()
    timestamp = datetime.now().isoformat()

    missing_paths = check_required_paths()

    result = {
        "timestamp": timestamp,
        "status": "PASS" if not missing_paths else "FAIL",
        "missing_paths": missing_paths,
        "root_directory": str(PRIMUS_ROOT),
        "system_directory": str(ROOT_DIR),
        "time_elapsed_sec": round(time.time() - start, 4),
    }

    log(result)
    return result


if __name__ == "__main__":
    output = run_selftest()
    print(json.dumps(output, indent=4))
