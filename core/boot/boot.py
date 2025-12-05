"""
PRIMUS OS - Boot Module (Milestone 2)
Loads system configs and returns boot state to the master controller.
"""
from pathlib import Path
import json


SYSTEM_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = SYSTEM_ROOT / "configs" / "system_paths.json"


def boot_system():
    """
    Load ``system_paths.json`` from the System/configs directory and return a
    normalized dictionary describing the boot configuration.

    Returns a dict with keys:
    - status: "ok" or "error"
    - config_path: resolved path to the config file
    - paths: parsed JSON payload (on success)
    - error: error message (on failure)
    """

    if not CONFIG_PATH.exists():
        return {
            "status": "error",
            "error": f"system_paths.json not found at {CONFIG_PATH}",
        }

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive logging path
        return {
            "status": "error",
            "error": f"Failed to read system_paths.json: {exc}",
        }

    return {"status": "ok", "config_path": str(CONFIG_PATH), "paths": data}


# manual debug mode
if __name__ == "__main__":
    print(boot_system())
