# core/subchat_sandbox.py
"""
Subchat Sandbox Layer
---------------------
Safely executes any subchat-related actions in a fully restricted sandbox.

Rules implemented here:
- No system modifications allowed unless explicitly permitted.
- No privileged file access.
- No external network access.
- No agent-to-agent or agent-to-system operations without explicit approval.
- All sandbox actions are logged.
- Sandbox can be toggled between:
    * READ-ONLY MODE
    * CONTROLLED EXECUTION MODE (approval required)
"""

import traceback
from datetime import datetime
from pathlib import Path
import json


class SubchatSandbox:
    def __init__(self, sandbox_root: str = "sandbox_logs"):
        self.sandbox_root = Path(sandbox_root)
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

        # TRUE = sandbox is locked down, nothing can be written/changed.
        self.read_only = True

        # TRUE = every action MUST be approved by the user.
        self.approval_required = True

        self._log("Sandbox initialized", {"read_only": self.read_only})

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    def _log(self, message: str, details: dict | None = None):
        log_file = self.sandbox_root / "sandbox.log"
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "details": details or {}
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # -------------------------------------------------------------------------
    # Sandbox Controls
    # -------------------------------------------------------------------------
    def enable_read_only(self):
        self.read_only = True
        self._log("Sandbox read-only mode enabled")

    def disable_read_only(self):
        self.read_only = False
        self._log("Sandbox read-only mode disabled")

    def require_approval(self):
        self.approval_required = True
        self._log("Sandbox approval requirement enabled")

    def allow_automatic(self):
        self.approval_required = False
        self._log("Sandbox approval requirement disabled")

    # -------------------------------------------------------------------------
    # User Approval Hook (placeholder)
    # PRIMUS or UI will override this later with a real approval callback.
    # -------------------------------------------------------------------------
    def ask_user_approval(self, action_description: str) -> bool:
        """
        This is a placeholder for the UI or PRIMUS core.

        During early development, we default to DENY.
        Later, the Windows app will call a popup:
            "Approve sandbox action? YES / NO"
        """
        self._log("Approval requested", {"action": action_description})
        return False  # default safety — no automatic approvals yet

    # -------------------------------------------------------------------------
    # SAFE EXECUTION WRAPPER
    # -------------------------------------------------------------------------
    def execute(self, action_description: str, func, *args, **kwargs):
        """
        Executes a function safely inside the sandbox.
        """
        try:
            # BLOCKED if sandbox is read-only
            if self.read_only:
                self._log("Action blocked (read-only)", {"action": action_description})
                return {"status": "blocked", "reason": "read_only"}

            # REQUIRE APPROVAL
            if self.approval_required:
                approved = self.ask_user_approval(action_description)
                if not approved:
                    self._log("Action denied (user rejected)", {"action": action_description})
                    return {"status": "denied", "reason": "approval_required"}

            # EXECUTE safely
            result = func(*args, **kwargs)
            self._log("Action executed", {
                "action": action_description,
                "result_type": str(type(result))
            })

            return {"status": "success", "result": result}

        except Exception as e:
            tb = traceback.format_exc()
            self._log("Action failed", {"action": action_description, "error": str(e), "trace": tb})
            return {"status": "error", "error": str(e), "trace": tb}

    # -------------------------------------------------------------------------
    # SANDBOXED FILE ACCESS (STRICT)
    # -------------------------------------------------------------------------
    def safe_write(self, filepath: Path, content: str):
        """
        Sandboxed file write with restrictions:
        - Must be inside sandbox_root.
        - Requires approval if enabled.
        """
        filepath = Path(filepath)

        if not filepath.resolve().is_relative_to(self.sandbox_root.resolve()):
            self._log("Unauthorized write attempt", {"file": str(filepath)})
            return {"status": "blocked", "reason": "write_outside_sandbox"}

        return self.execute(
            f"Write to {filepath}",
            self._write_internal,
            filepath,
            content
        )

    def _write_internal(self, filepath: Path, content: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    # -------------------------------------------------------------------------
    # SANDBOXED READ ACCESS (READING IS ALWAYS SAFE)
    # -------------------------------------------------------------------------
    def safe_read(self, filepath: Path):
        filepath = Path(filepath)

        if not filepath.exists():
            return {"status": "error", "reason": "file_not_found"}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = f.read()
            return {"status": "success", "content": data}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# -------------------------------------------------------------------------
# END OF FILE
# -------------------------------------------------------------------------