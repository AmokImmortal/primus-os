"""
PRIMUS OS — Boot Validator (Milestone 2)
Simple sanity checks on system_paths.json and required directories.
"""
from pathlib import Path
import json

SYSTEM_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = SYSTEM_ROOT / "configs" / "system_paths.json"

REQUIRED_KEYS = [
    "root",
    "core_boot",
    "intelligence_dispatcher",
    "agents",
    "logs",
    "captains_log_vault",
    "checkpoints",
    "rag",
    "interfaces",
]


def _resolve_path(cfg: dict, key: str, root_path: Path) -> Path:
    raw = cfg.get(key)
    if raw is None:
        return Path()
    path = Path(raw)
    if key == "root":
        return path if path.is_absolute() else (SYSTEM_ROOT.parent / path).resolve()
    if not path.is_absolute():
        path = root_path / path
    return path.resolve()


def validate_paths():
    """
    Returns (ok: bool, info: dict)
    info contains errors or success details.
    """
    if not CONFIG_PATH.exists():
        return False, {"error": f"Missing config file: {CONFIG_PATH}"}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as exc:
        return False, {"error": f"Failed to read config: {exc}"}

    missing_keys = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing_keys:
        return False, {"error": "Missing required config keys", "missing_keys": missing_keys}

    root_path = _resolve_path(cfg, "root", SYSTEM_ROOT)

    missing_paths = []
    for key in REQUIRED_KEYS:
        path = _resolve_path(cfg, key, root_path)
        if not path.exists():
            missing_paths.append({key: str(path)})

    if missing_paths:
        return False, {"error": "Missing filesystem paths", "missing_paths": missing_paths}

    return True, {"message": "All required paths present"}


def run_validator():
    ok, info = validate_paths()
    if ok:
        print("[boot_validator] OK:", info.get("message"))
    else:
        print("[boot_validator] FAIL:", info)


if __name__ == "__main__":
    run_validator()
