# security_layer.py
"""
Security layer for PRIMUS OS

Location example:
C:\P.R.I.M.U.S OS\System\security\security_layer.py

Responsibilities:
- Manage Sandbox / Captain's Log mode (enter/exit, state)
- Enforce permissions for agents and system components
- Basic password/PIN management (hashed) and optional security questions
- Approval workflow for actions that require human confirmation
- Prevent unauthorized write/read to protected areas (e.g., captain's log)
- Logging hooks (success/failure) — logs are written to core/system_logs by caller
- Keep all data local and persisted to configs/security.json

Notes:
- This module is intentionally conservative and synchronous (no async).
- It uses PBKDF2-HMAC-SHA256 for password hashing (secure and available in stdlib).
- This does not implement any network or online features.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import hmac
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable

# -------------------------
# Paths / Defaults
# -------------------------
SYSTEM_ROOT = Path(__file__).resolve().parents[2]  # .../System/security -> parents[2] -> System
CONFIG_DIR = SYSTEM_ROOT / "configs"
SECURITY_CONFIG_PATH = CONFIG_DIR / "security.json"

# Protected folders (agents should NOT write here unless sandboxed)
PROTECTED_FOLDERS = {
    "captains_log": str(SYSTEM_ROOT / "captains_log"),  # sandbox area
    "core": str(SYSTEM_ROOT / "core"),
    "configs": str(CONFIG_DIR),
}

# Default security template
DEFAULT_CONFIG = {
    "sandbox": {
        "enabled": False,
        "entered_at": None,
        "entered_by": None  # user metadata if desired
    },
    "auth": {
        "password_hash": None,
        "password_salt": None,
        "pin_hash": None,
        "pin_salt": None,
        "security_questions": []  # list of {"q": "...", "answer_hash": "...", "salt": "..."}
    },
    "policies": {
        # Example policy entries:
        # "agent_name": {"can_read_rag": True, "can_write_rag": False, "max_agents_collab": 2}
    },
    "pending_approvals": {
        # uuid: { "action": "...", "requester": "...", "created_at": ..., "metadata": {...} }
    }
}


# -------------------------
# Utility: hashing
# -------------------------
def _gen_salt() -> str:
    return uuid.uuid4().hex


def _hash_password(password: str, salt: str, iterations: int = 200_000) -> str:
    if password is None:
        return ""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return dk.hex()


def _verify_password(password: str, salt: str, correct_hash: str) -> bool:
    if not correct_hash or not salt:
        return False
    return hmac.compare_digest(_hash_password(password, salt), correct_hash)


# -------------------------
# Exceptions
# -------------------------
class SecurityError(Exception):
    pass


class PermissionDenied(SecurityError):
    pass


# -------------------------
# Approval manager
# -------------------------
class ApprovalManager:
    """
    Tracks pending approvals and allows an external process (UI / human) to approve/deny.
    """

    def __init__(self, storage: Dict[str, Any]):
        # storage is a reference to config['pending_approvals']
        self._storage = storage

    def request_approval(self, action: str, requester: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        req_id = str(uuid.uuid4())
        self._storage[req_id] = {
            "action": action,
            "requester": requester,
            "metadata": metadata or {},
            "created_at": int(time.time()),
            "status": "pending"
        }
        return req_id

    def list_pending(self) -> Dict[str, Any]:
        return {k: v for k, v in self._storage.items() if v.get("status") == "pending"}

    def set_approval(self, req_id: str, approved: bool, approver: Optional[str] = None) -> bool:
        item = self._storage.get(req_id)
        if not item:
            return False
        item["status"] = "approved" if approved else "denied"
        item["resolved_by"] = approver
        item["resolved_at"] = int(time.time())
        return True

    def get(self, req_id: str) -> Optional[Dict[str, Any]]:
        return self._storage.get(req_id)


# -------------------------
# SecurityLayer
# -------------------------
class SecurityLayer:
    """
    Main interface used by system components and agents.
    Example usage:
        sec = SecurityLayer()
        sec.load()
        sec.set_password("hunter2")
        sec.enter_sandbox(password="hunter2")
        sec.can_agent_write(agent_name, '/path/to/file')
    """

    def __init__(self):
        self._config_path = SECURITY_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self._loaded = False
        self.approval = None

        # In-memory runtime-only lock to avoid concurrent operations within the same process
        self._runtime_lock = False

        # Ensure config dir exists
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Persistence
    # -------------------------
    def load(self) -> None:
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except Exception:
                # fallback to default if corrupt
                self._config = DEFAULT_CONFIG.copy()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self._save()
        # Ensure approval manager uses the persistent pending approvals dict
        self.approval = ApprovalManager(self._config.setdefault("pending_approvals", {}))
        self._loaded = True

    def _save(self) -> None:
        # Atomic-ish write
        tmp = str(self._config_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)
        os.replace(tmp, str(self._config_path))

    # -------------------------
    # Auth management
    # -------------------------
    def set_password(self, password: str) -> None:
        """Set user password (PBKDF2 hashed)."""
        salt = _gen_salt()
        phash = _hash_password(password, salt)
        self._config.setdefault("auth", {})
        self._config["auth"]["password_hash"] = phash
        self._config["auth"]["password_salt"] = salt
        self._save()

    def verify_password(self, password: str) -> bool:
        auth = self._config.get("auth", {})
        return _verify_password(password, auth.get("password_salt", ""), auth.get("password_hash", ""))

    def set_pin(self, pin: str) -> None:
        if len(pin) < 4:
            raise SecurityError("PIN must be at least 4 characters")
        salt = _gen_salt()
        phash = _hash_password(pin, salt)
        self._config.setdefault("auth", {})
        self._config["auth"]["pin_hash"] = phash
        self._config["auth"]["pin_salt"] = salt
        self._save()

    def verify_pin(self, pin: str) -> bool:
        auth = self._config.get("auth", {})
        return _verify_password(pin, auth.get("pin_salt", ""), auth.get("pin_hash", ""))

    def add_security_question(self, question: str, answer: str) -> None:
        salt = _gen_salt()
        ahash = _hash_password(answer, salt)
        self._config.setdefault("auth", {})
        qlist = self._config["auth"].setdefault("security_questions", [])
        qlist.append({"q": question, "answer_hash": ahash, "salt": salt})
        self._save()

    def verify_security_answers(self, answers: List[Tuple[int, str]]) -> bool:
        """
        answers: list of (index, answer)
        Return True only if all provided answers match.
        """
        qlist = self._config.get("auth", {}).get("security_questions", [])
        for idx, ans in answers:
            if idx < 0 or idx >= len(qlist):
                return False
            if not _verify_password(ans, qlist[idx]["salt"], qlist[idx]["answer_hash"]):
                return False
        return True

    # -------------------------
    # Sandbox management
    # -------------------------
    def enter_sandbox(self, password: str, entered_by: Optional[str] = None) -> bool:
        """
        Enter Captain's Log sandbox mode. Requires password.
        When sandbox is active:
          - Write access to protected folders is allowed only for sandbox processes.
          - Additional root capabilities are available (controlled elsewhere).
        """
        if not self.verify_password(password):
            return False
        self._config.setdefault("sandbox", {})
        self._config["sandbox"]["enabled"] = True
        self._config["sandbox"]["entered_at"] = int(time.time())
        self._config["sandbox"]["entered_by"] = entered_by
        self._save()
        return True

    def exit_sandbox(self, require_approval: bool = False) -> bool:
        """
        Exit sandbox. Optionally require an approval step (for forced exit or audit).
        """
        self._config.setdefault("sandbox", {})
        self._config["sandbox"]["enabled"] = False
        self._config["sandbox"]["entered_at"] = None
        self._config["sandbox"]["entered_by"] = None
        self._save()
        return True

    def is_sandbox_active(self) -> bool:
        return bool(self._config.get("sandbox", {}).get("enabled", False))

    # -------------------------
    # Policy management
    # -------------------------
    def set_agent_policy(self, agent_name: str, policy: Dict[str, Any]) -> None:
        self._config.setdefault("policies", {})
        self._config["policies"][agent_name] = policy
        self._save()

    def get_agent_policy(self, agent_name: str) -> Dict[str, Any]:
        return self._config.get("policies", {}).get(agent_name, {})

    # -------------------------
    # Permission checks
    # -------------------------
    def _is_path_protected(self, path: str) -> Optional[str]:
        """
        Returns the protected key name if the path falls under a protected folder, else None.
        """
        path = os.path.abspath(path)
        for name, p in PROTECTED_FOLDERS.items():
            try:
                # canonical compare
                if os.path.commonpath([path, os.path.abspath(p)]) == os.path.abspath(p):
                    return name
            except Exception:
                continue
        return None

    def can_agent_read(self, agent_name: str, path: str) -> bool:
        """
        Agents may read from certain areas depending on policy.
        - For captains_log: only when sandbox active and agent policy allows it (or special exception).
        """
        prot = self._is_path_protected(path)
        if not prot:
            return True

        if prot == "captains_log":
            # captains log is private unless sandbox
            if not self.is_sandbox_active():
                return False
            # if sandbox active, agent still needs explicit allow
            policy = self.get_agent_policy(agent_name)
            return bool(policy.get("can_read_captains_log", False))

        # For core and configs: read may be allowed but carefully; default deny
        policy = self.get_agent_policy(agent_name)
        return bool(policy.get("can_read_core", False))

    def can_agent_write(self, agent_name: str, path: str) -> bool:
        """
        Agents may write only into their own folders or permitted rag folders.
        - Captains log: never writable unless sandbox and agent explicitly allowed AND action approved.
        """
        prot = self._is_path_protected(path)
        if not prot:
            # allow writing into non-protected areas by default policy
            policy = self.get_agent_policy(agent_name)
            return bool(policy.get("can_write_unprotected", True))

        if prot == "captains_log":
            # never write unless sandbox+policy+approval
            if not self.is_sandbox_active():
                return False
            policy = self.get_agent_policy(agent_name)
            if not policy.get("can_write_captains_log", False):
                return False
            # require explicit approval for write actions into captain's log
            return False  # require approval pipeline (request_approval) — higher-level caller should enforce

        # core/configs should never be written by agents
        return False

    # -------------------------
    # Approval workflow helpers
    # -------------------------
    def request_approval_for_action(self, action: str, requester: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Convenience wrapper to request an approval. Returns request id.
        """
        return self.approval.request_approval(action=action, requester=requester, metadata=metadata)

    def approve_request(self, req_id: str, approver: Optional[str] = None) -> bool:
        return self.approval.set_approval(req_id, True, approver)

    def deny_request(self, req_id: str, approver: Optional[str] = None) -> bool:
        return self.approval.set_approval(req_id, False, approver)

    # -------------------------
    # Redaction helper
    # -------------------------
    def redact_for_external(self, text: str, allowed_keys: Optional[List[str]] = None) -> str:
        """
        Basic redaction stub. For now, this replaces occurrences of configured protected keywords,
        file paths, and system names. This should be extended with robust PII detection later.
        """
        if not text:
            return text
        redacted = text
        # redact paths to protected folders
        for key, p in PROTECTED_FOLDERS.items():
            redacted = redacted.replace(p, "[REDACTED_PATH]")
        # redact system root
        redacted = redacted.replace(str(SYSTEM_ROOT), "[SYSTEM_ROOT]")
        # basic keyword redaction if present in config (optional)
        for kw in self._config.get("redact_keywords", []):
            redacted = redacted.replace(kw, "[REDACTED]")
        return redacted

    # -------------------------
    # Decorator for sensitive operations
    # -------------------------
    def require_approval(self, action_name: str) -> Callable:
        """
        Decorator to mark functions that require approval before executing.
        Usage:
            @sec.require_approval("write_captains_log")
            def dangerous(...):
                ...
        The decorator will check pending approvals for a matching item and only run
        the function if its request id is approved.
        """

        def decorator(fn: Callable):
            def wrapper(*args, _approval_id: Optional[str] = None, **kwargs):
                if _approval_id is None:
                    raise PermissionDenied("Action requires approval request id.")
                info = self.approval.get(_approval_id)
                if not info or info.get("status") != "approved":
                    raise PermissionDenied("Approval not found or not approved.")
                # proceed
                return fn(*args, **kwargs)

            wrapper.__name__ = fn.__name__
            return wrapper

        return decorator

    # -------------------------
    # Info / utilities
    # -------------------------
    def info(self) -> Dict[str, Any]:
        return {
            "sandbox_active": self.is_sandbox_active(),
            "policies": list(self._config.get("policies", {}).keys()),
            "pending_approvals": len(self.approval.list_pending())
        }


# -------------------------
# On import, create/load default instance for convenience (can be overridden)
# -------------------------
_default_security_layer: Optional[SecurityLayer] = None


def get_security_layer() -> SecurityLayer:
    global _default_security_layer
    if _default_security_layer is None:
        sl = SecurityLayer()
        sl.load()
        _default_security_layer = sl
    return _default_security_layer


# -------------------------
# Simple CLI test (non-invasive)
# -------------------------
if __name__ == "__main__":
    sec = get_security_layer()
    print("Security layer loaded. Sandbox active:", sec.is_sandbox_active())
    # If no password is set, set a sample one (only for first-time local runs)
    auth = sec._config.get("auth", {})
    if not auth.get("password_hash"):
        print("No password configured. Use 'set_password' to initialize.")
    else:
        print("Password protection configured.")