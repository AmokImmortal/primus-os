import os
import json
import traceback
from pathlib import Path

from core.captains_log_manager import CaptainsLogManager


class CaptainsLogBoot:
    """
    Boot loader for Captain’s Log Sandbox Mode.
    Runs BEFORE Primus initializes.
    Handles:
      • Isolation (no internet)
      • Password access
      • Sandbox environment setup
      • Full root control gating
    """

    def __init__(self):
        self.root = Path(__file__).resolve().parent.parent
        self.config_path = self.root / "system" / "captains_log_config.json"
        self.manager = None
        self.active = False

    def load_config(self):
        """Load captain’s log config file."""
        try:
            if not self.config_path.exists():
                return {
                    "password_hash": None,
                    "requires_password": True,
                    "security_questions": {},
                    "sandbox_enabled": True
                }

            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("[Captain’s Log Boot] ERROR loading config:")
            traceback.print_exc()
            return {
                "password_hash": None,
                "requires_password": True,
                "security_questions": {},
                "sandbox_enabled": True
            }

    def block_internet(self):
        """
        PREVENT Primus from using external requests.
        This is toggled OFF for Captain’s Log Mode.
        """
        os.environ["PRIMUS_NET_DISABLED"] = "1"

    def allow_internet(self):
        """Restore internet availability after sandbox exit."""
        os.environ["PRIMUS_NET_DISABLED"] = "0"

    def verify_password(self, config):
        """Check password / security gate before entering sandbox."""
        if not config.get("requires_password", True):
            return True

        stored_hash = config.get("password_hash")
        if stored_hash is None:
            print("[Captain’s Log Boot] No password set — create one in config.")
            return False

        import hashlib
        pwd = input("Enter Captain’s Log password: ").strip()
        entered_hash = hashlib.sha256(pwd.encode()).hexdigest()

        return entered_hash == stored_hash

    def enter_sandbox(self):
        """Enable Captain’s Log mode, set flags, initialize manager."""
        self.block_internet()  # force isolation

        print("\n--- CAPTAIN’S LOG SANDBOX MODE ENABLED ---")
        self.active = True

        self.manager = CaptainsLogManager()
        self.manager.initialize()

        # Full Root Control — but only inside sandbox
        os.environ["PRIMUS_ROOT_OVERRIDE"] = "1"

        return True

    def exit_sandbox(self):
        """Turn off sandbox and restore system defaults."""
        self.allow_internet()
        os.environ["PRIMUS_ROOT_OVERRIDE"] = "0"
        self.active = False

    def boot(self):
        """Main boot sequence run BEFORE Primus."""
        try:
            config = self.load_config()

            if not config.get("sandbox_enabled", True):
                print("[Captain’s Log Boot] Sandbox disabled in config.")
                return False

            print("Captain’s Log Sandbox detected. Access locked.")

            if not self.verify_password(config):
                print("Access denied.")
                return False

            return self.enter_sandbox()

        except Exception:
            print("[Captain’s Log Boot] CRITICAL ERROR during boot:")
            traceback.print_exc()
            return False


# If this file is run directly:
if __name__ == "__main__":
    boot = CaptainsLogBoot()
    if boot.boot():
        print("Sandbox boot successful.")
    else:
        print("Sandbox not activated.")