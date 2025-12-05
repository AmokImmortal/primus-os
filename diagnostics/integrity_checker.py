import json
import hashlib
import traceback
from pathlib import Path

SYSTEM_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FOLDERS = [
    "core",
    "rag",
    "agents",
    "captains_log_vault",
    "checkpoints",
    "interfaces",
    "diagnostics",
    "security",
    "configs",
    "logs",
]

REQUIRED_FILES = [
    "core/engine.py",
    "core/agent_manager.py",
    "core/session_manager.py",
    "core/persona.py",
    "core/primus_runtime.py",
    "core/primus_bridge.py",
    "core/rag_manager.py",
    "core/captains_log_manager.py",
    "core/boot/boot.py",
    "core/boot/boot_validator.py",
    "core/boot/boot_logger.py",
    "primus_cli.py",
    "configs/system_paths.json",
    "diagnostics/selftest.py",
]

# Folders requiring restricted read/write rules
PROTECTED_FOLDERS = {
    "captains_log_vault": {"read": ["you"], "write": ["you"], "locked_for_primus": True},
}

# Expected JSON files to validate format
JSON_FILES = [
    "personality.json",
    "configs/system_paths.json",
]


def hash_file(filepath: Path):
    try:
        sha256 = hashlib.sha256()
        with filepath.open("rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


def folder_exists(path):
    return (SYSTEM_ROOT / path).exists()


def file_exists(path):
    return (SYSTEM_ROOT / path).is_file()


def validate_json_file(path):
    try:
        with open(SYSTEM_ROOT / path, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        return False


def check_protected_folders():
    results = {}
    for folder, rules in PROTECTED_FOLDERS.items():
        full = SYSTEM_ROOT / folder
        status = {}

        status["exists"] = full.exists()

        sentinel = full / ".primus_no_write"
        status["write_protected_flag"] = sentinel.exists()

        results[folder] = status

    return results


def run_integrity_check():
    report = {
        "folders": {},
        "files": {},
        "protected_folders": {},
        "json_validation": {},
        "hashes": {},
        "errors": []
    }

    try:
        for folder in REQUIRED_FOLDERS:
            report["folders"][folder] = folder_exists(folder)

        for file in REQUIRED_FILES:
            exists = file_exists(file)
            report["files"][file] = exists
            if exists:
                report["hashes"][file] = hash_file(SYSTEM_ROOT / file)

        report["protected_folders"] = check_protected_folders()

        for jf in JSON_FILES:
            report["json_validation"][jf] = validate_json_file(jf)

    except Exception:
        report["errors"].append(traceback.format_exc())

    return report


if __name__ == "__main__":
    report = run_integrity_check()
    print(json.dumps(report, indent=4))
