"""
core/security_enforcer.py

Centralized enforcement layer for PRIMUS OS.
Responsibilities:
- Centralize permission checks for actions (read/write/execute/remote) requested by agents, PRIMUS, or UI.
- Enforce Captain's Log isolation and sandboxing rules.
- Offer approval workflow for sensitive actions.
- Provide redaction helpers and rule-based redaction.
- Log enforcement decisions for audit/debug (to core/system_logs or logs/).
- Simple JSON-backed policy store so policies can be modified without changing code.

Design goals:
- Minimal external dependencies (only stdlib).
- Clear, well-documented functions so other modules can call:
    se = SecurityEnforcer.get()
    res = se.enforce(actor="AgentX", action="write_file", resource="/path/to/file", data=payload)
- Non-blocking by default: returns a dict with status: ok | denied | pending
"""

from __future__ import annotations
import json
import re
import uuid
import time
from pathlib import Path
from typing import Any, Dict, Optional, Callable

SYSTEM_ROOT = Path(__file__).resolve().parents[2]  # ../../ (System)
CONFIGS_DIR = SYSTEM_ROOT / "configs"
LOGS_DIR = SYSTEM_ROOT / "logs"
CORE_LOGS_DIR = SYSTEM_ROOT / "core" / "system_logs"

POLICIES_FILE = CONFIGS_DIR / "security_policies.json"
ENFORCER_LOG = CORE_LOGS_DIR / "security_enforcer.log"

# default policy template (used if no policy file exists)
DEFAULT_POLICIES = {
    "global": {
        "agents_allowed_to_write_system": [],  # list of agent names
        "allow_agent_to_agent_communication": False,
        "max_concurrent_agent_pairs": 2,
        "rag": {
            "agents_read_allowed": True,
            "agents_write_allowed": False,
            "private_rag_patterns": ["captains_log"]
        },
        "sensitive_file_patterns": [
            r".*primus_master.*",
            r".*primus_kernel.*",
            r".*core.*",
            r".*password.*",
            r".*secret.*"
        ],
        "redaction_patterns": [
            # Tuples: (pattern, replacement)
            [r"\b(?:\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})\b", "[REDACTED_CARD]"],
            [r"\b(?:\d{3}[- ]?\d{2}[- ]?\d{4})\b", "[REDACTED_SSN]"],
            [r"(?i)password\s*[:=]\s*\S+", "password: [REDACTED]"]
        ],
        "approval_required_actions": [
            "external_api_call",
            "write_system_file",
            "modify_agent_personality",
            "execute_remote_code"
        ]
    }
}


def _ensure_dirs():
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CORE_LOGS_DIR.mkdir(parents=True, exist_ok=True)


class SecurityEnforcer:
    """
    Singleton enforcement layer. Use SecurityEnforcer.get() to obtain instance.
    """

    _instance: Optional["SecurityEnforcer"] = None

    @classmethod
    def get(cls) -> "SecurityEnforcer":
        if cls._instance is None:
            cls._instance = SecurityEnforcer()
        return cls._instance

    def __init__(self):
        _ensure_dirs()
        self.policies = self._load_policies()
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}  # token -> approval info
        # callback signature: (approval_info: dict) -> bool (True=approved)
        self.approval_callback: Optional[Callable[[Dict[str, Any]], bool]] = None

    # -------------------------
    # Policy load/save
    # -------------------------
    def _load_policies(self) -> Dict[str, Any]:
        if POLICIES_FILE.exists():
            try:
                with open(POLICIES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Basic validation fallback
                    if not isinstance(data, dict):
                        self._write_default_policies()
                        return DEFAULT_POLICIES.copy()
                    return data
            except Exception as e:
                self._log(f"Failed to load policies: {e}")
                self._write_default_policies()
                return DEFAULT_POLICIES.copy()
        else:
            self._write_default_policies()
            return DEFAULT_POLICIES.copy()

    def _write_default_policies(self):
        try:
            with open(POLICIES_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_POLICIES, f, indent=2)
            self._log("Default security policies written.")
        except Exception as e:
            self._log(f"Failed writing default policies: {e}")

    def reload_policies(self):
        self.policies = self._load_policies()
        self._log("Policies reloaded.")

    def save_policies(self):
        try:
            with open(POLICIES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.policies, f, indent=2)
            self._log("Policies saved.")
            return True
        except Exception as e:
            self._log(f"Failed saving policies: {e}")
            return False

    # -------------------------
    # Logging
    # -------------------------
    def _log(self, message: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        try:
            with open(ENFORCER_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            # best-effort fallback to prints (should rarely happen)
            print(f"[SecurityEnforcer Log Failure] {ts} {message}")

    # -------------------------
    # Approval flow
    # -------------------------
    def set_approval_callback(self, cb: Callable[[Dict[str, Any]], bool]):
        """
        Allows host application to wire a synchronous approval UI or automation.
        The callback receives approval_info and returns True/False.
        """
        self.approval_callback = cb

    def request_approval(self, actor: str, action: str, resource: str, reason: str, extra: Optional[Dict] = None) -> Dict[str, Any]:
        token = str(uuid.uuid4())
        info = {
            "token": token,
            "actor": actor,
            "action": action,
            "resource": resource,
            "reason": reason,
            "extra": extra or {},
            "status": "pending",
            "created_at": time.time()
        }
        self.pending_approvals[token] = info
        self._log(f"Approval requested: {actor} -> {action} on {resource} (token={token})")

        # If a callback is registered, call it synchronously
        if self.approval_callback is not None:
            try:
                decision = bool(self.approval_callback(info))
                if decision:
                    self.approve(token, approver="system_callback")
                else:
                    self.deny(token, approver="system_callback")
            except Exception as e:
                self._log(f"Approval callback error: {e}")

        return {"status": "pending", "token": token, "info": info}

    def approve(self, token: str, approver: str = "owner") -> Dict[str, Any]:
        info = self.pending_approvals.get(token)
        if not info:
            return {"status": "error", "error": "invalid_token"}
        info["status"] = "approved"
        info["approved_by"] = approver
        info["approved_at"] = time.time()
        self._log(f"Approval granted: token={token} by {approver}")
        return {"status": "ok", "token": token}

    def deny(self, token: str, approver: str = "owner") -> Dict[str, Any]:
        info = self.pending_approvals.get(token)
        if not info:
            return {"status": "error", "error": "invalid_token"}
        info["status"] = "denied"
        info["denied_by"] = approver
        info["denied_at"] = time.time()
        self._log(f"Approval denied: token={token} by {approver}")
        return {"status": "ok", "token": token}

    # -------------------------
    # Redaction helpers
    # -------------------------
    def redact(self, text: str) -> str:
        """
        Apply configured redaction patterns to the provided text.
        Patterns in policies['global']['redaction_patterns'] are applied in order.
        Each entry is [pattern, replacement].
        """
        try:
            patterns = self.policies.get("global", {}).get("redaction_patterns", [])
            s = text
            for pat, repl in patterns:
                s = re.sub(pat, repl, s)
            return s
        except Exception as e:
            self._log(f"Redaction error: {e}")
            return text

    # -------------------------
    # Helper checks
    # -------------------------
    def _is_in_captains_log(self, resource: str) -> bool:
        # If resource path contains any private rag token or captains_log configured name, treat as captain's log
        private_patterns = self.policies.get("global", {}).get("rag", {}).get("private_rag_patterns", [])
        for p in private_patterns:
            if p in resource.replace("\\", "/"):
                return True
        # Also consider a dedicated folder path under SYSTEM_ROOT/captains_log (if exists)
        cap_path = SYSTEM_ROOT / "captains_log"
        try:
            resource_path = Path(resource)
            if cap_path.exists() and cap_path in resource_path.parents:
                return True
        except Exception:
            pass
        return False

    def _matches_sensitive(self, resource: str) -> bool:
        patterns = self.policies.get("global", {}).get("sensitive_file_patterns", [])
        for pat in patterns:
            try:
                if re.search(pat, resource, flags=re.IGNORECASE):
                    return True
            except Exception:
                # ignore invalid patterns
                continue
        return False

    # -------------------------
    # Core enforcement
    # -------------------------
    def enforce(self, actor: str, action: str, resource: str, data: Any = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main enforcement entrypoint.
        actor: agent name, "PRIMUS", or username
        action: string, e.g. "read_file", "write_file", "external_api_call"
        resource: path or resource identifier (string)
        data: optional payload for inspection (text, etc.)
        context: optional dict with extra info

        Returns dict:
        {
            "status": "ok" | "denied" | "pending",
            "reason": str,
            "approval_token": str|null,
            "payload": optional (e.g. redacted data)
        }
        """
        context = context or {}
        resource_str = str(resource)

        # 1) Captain's log isolation: Only allowed by explicit policy or if actor == "CAPTAIN"
        if self._is_in_captains_log(resource_str):
            # if actor is not explicitly allowed, deny or request approval
            allowed_list = self.policies.get("global", {}).get("agents_allowed_to_write_system", [])
            if actor not in allowed_list and actor != "CAPTAIN" and actor != "PRIMUS_OWNER":
                self._log(f"Denied {actor} -> {action} on captain's log {resource_str}")
                return {"status": "denied", "reason": "captains_log_protected"}

        # 2) RAG access rules
        if "/rag/" in resource_str.replace("\\", "/"):
            rag_cfg = self.policies.get("global", {}).get("rag", {})
            if action.startswith("write") and not rag_cfg.get("agents_write_allowed", False):
                # if trying to write to RAG, deny unless actor in allowed list
                if actor not in self.policies.get("global", {}).get("agents_allowed_to_write_system", []):
                    self._log(f"Denied RAG write: {actor} -> {resource_str}")
                    return {"status": "denied", "reason": "rag_write_forbidden"}
            if action.startswith("read") and not rag_cfg.get("agents_read_allowed", True):
                self._log(f"Denied RAG read: {actor} -> {resource_str}")
                return {"status": "denied", "reason": "rag_read_forbidden"}

        # 3) Sensitive file protection
        if self._matches_sensitive(resource_str):
            # If action is write or modify, require explicit approval
            if action.startswith("write") or action.startswith("modify") or action == "execute_remote_code":
                if actor not in self.policies.get("global", {}).get("agents_allowed_to_write_system", []):
                    # Request approval
                    if action in self.policies.get("global", {}).get("approval_required_actions", []):
                        r = self.request_approval(actor, action, resource_str, reason="sensitive_action", extra={"context": context})
                        return {"status": "pending", "reason": "approval_required", "approval_token": r["token"]}
                    else:
                        self._log(f"Denied sensitive action: {actor} -> {action} on {resource_str}")
                        return {"status": "denied", "reason": "sensitive_protected"}

        # 4) External API restriction
        if action == "external_api_call":
            # default: require approval
            if action in self.policies.get("global", {}).get("approval_required_actions", []):
                r = self.request_approval(actor, action, resource_str, reason="external_call", extra={"context": context})
                return {"status": "pending", "approval_token": r["token"], "reason": "external_api_approval_required"}

        # 5) Agent-to-agent communication guard
        if action == "agent_to_agent_message":
            allow = self.policies.get("global", {}).get("allow_agent_to_agent_communication", False)
            if not allow:
                self._log(f"Denied agent->agent: {actor} attempted {action}")
                return {"status": "denied", "reason": "agent_to_agent_disabled"}

        # 6) Data redaction on outbound (best-effort)
        payload = None
        if isinstance(data, str):
            # If resource is external/shared, redact sensitive fields before sending
            payload = self.redact(data)

        # 7) If no rule matched, allow
        self._log(f"Allowed: {actor} -> {action} on {resource_str}")
        return {"status": "ok", "reason": "allowed", "payload": payload}

    # -------------------------
    # Convenience utilities
    # -------------------------
    def is_action_allowed(self, actor: str, action: str, resource: str) -> bool:
        r = self.enforce(actor, action, resource, data=None)
        return r.get("status") == "ok"

    def get_pending_approvals(self) -> Dict[str, Dict[str, Any]]:
        return self.pending_approvals.copy()

    def clear_stale_approvals(self, older_than_seconds: int = 3600):
        now = time.time()
        stale = [t for t, i in self.pending_approvals.items() if (now - i.get("created_at", 0)) > older_than_seconds]
        for t in stale:
            self.pending_approvals.pop(t, None)
            self._log(f"Cleared stale approval token: {t}")

    # -------------------------
    # Admin helpers (for unit tests / local CLI)
    # -------------------------
    def add_allowed_agent_for_system_writes(self, agent_name: str):
        al = self.policies.setdefault("global", {}).setdefault("agents_allowed_to_write_system", [])
        if agent_name not in al:
            al.append(agent_name)
            self.save_policies()
            self._log(f"Policy updated: added {agent_name} to agents_allowed_to_write_system")

    def remove_allowed_agent_for_system_writes(self, agent_name: str):
        al = self.policies.setdefault("global", {}).setdefault("agents_allowed_to_write_system", [])
        if agent_name in al:
            al.remove(agent_name)
            self.save_policies()
            self._log(f"Policy updated: removed {agent_name} from agents_allowed_to_write_system")


# Create module-level default instance for convenience imports:
_default_enforcer = SecurityEnforcer.get()


# Expose top-level functions to ease usage across the project
def enforce(actor: str, action: str, resource: str, data: Any = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _default_enforcer.enforce(actor, action, resource, data=data, context=context)


def request_approval(actor: str, action: str, resource: str, reason: str, extra: Optional[Dict] = None) -> Dict[str, Any]:
    return _default_enforcer.request_approval(actor, action, resource, reason, extra=extra)


def approve(token: str, approver: str = "owner") -> Dict[str, Any]:
    return _default_enforcer.approve(token, approver=approver)


def deny(token: str, approver: str = "owner") -> Dict[str, Any]:
    return _default_enforcer.deny(token, approver=approver)


def set_approval_callback(cb: Callable[[Dict[str, Any]], bool]):
    _default_enforcer.set_approval_callback(cb)