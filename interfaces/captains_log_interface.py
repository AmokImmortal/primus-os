"""
Captain's Log Interface Stub

This module provides a minimal interface wrapper that delegates to the core
Captain's Log manager once it exists. It is intentionally lightweight to keep
bootup self-tests satisfied without exposing Captain's Log data outside the
sandbox rules.
"""
from pathlib import Path
import sys

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = SYSTEM_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

try:  # pragma: no cover - defensive import for boot scaffolding
    from captains_log_manager import CaptainsLogManager  # type: ignore
except Exception:  # pragma: no cover - fallback placeholder
    class CaptainsLogManager:  # type: ignore
        """Placeholder manager used during early boot scaffolding."""

        def __init__(self):
            self.vault_path = SYSTEM_ROOT / "captains_log_vault"

        def open(self):
            return None


def get_captains_log_manager():
    """Return an instance of the Captain's Log manager (placeholder safe)."""
    try:
        return CaptainsLogManager()
    except Exception:
        return None
