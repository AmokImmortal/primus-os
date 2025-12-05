"""
core/subchat_security.py

Subchat security & access control for PRIMUS OS.

Responsibilities:
- Manage subchat metadata (private/public, owners, allowed agents, password protection, PINs)
- Verify access for users/agents (read / write / admin)
- Manage security questions for password reset (simple local flow)
- Persist metadata to core/sub_chats/subchat_meta.json
- Minimal external deps (uses stdlib only)
- Safe password storage (PBKDF2-HMAC + salt)
- Basic auditing hooks (access attempts) — emits events via optional logger callback

Storage layout (created automatically):
core/
  sub_chats/
    subchat_meta.json

Notes:
- This module is designed to be imported by higher-level managers (session_manager, captains_log_manager, etc.)
- Captain's Log sandbox mode / full-root features should still ask for explicit confirmation elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Constants
SYSTEM_CORE_DIR = Path(__file__).resolve().parents[1]  # core/
SUBCHAT_DIR = SYSTEM_CORE_DIR / "sub_chats"
META_PATH = SUBCHAT_DIR / "subchat_meta.json"

# PBKDF2 params
_PBKDF2_ITER = 200_000
_SALT_BYTES = 16
_HASH_NAME = "sha256"


def _ensure_storage():
    SUBCHAT_DIR.mkdir(parents=True, exist_ok=True)
    if not META_PATH.exists():
        META_PATH.write_text(json.dumps({"subchats": {}}), encoding="utf-8")


def _hash_password(password: str, salt: Optional[bytes] = None) -> Dict[str, Any]:
    """Return dict containing hex salt and hex derived key."""
    if salt is None:
        salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, _PBKDF2_ITER)
    return {"salt": salt.hex(), "dk": dk.hex(), "iterations": _PBKDF2_ITER, "algo": _HASH_NAME}


def _verify_password(password: str, salt_hex: str, dk_hex: str, iterations: int) -> bool:
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(dk_hex)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(dk, expected)


def _atomic_write(path: Path, obj: Any):
    """Safely write JSON to disk."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as tf:
        json.dump(obj, tf, indent=2, ensure_ascii=False)
        tf.flush()
        tmpname = tf.name
    os.replace(tmpname, str(path))


class SubchatSecurity:
    """Manage subchat security metadata and access logic."""

    def __init__(self, audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        _ensure_storage()
        self._audit = audit_callback
        self._data = self._load_all()

    # ----------------------------
    # Low-level I/O helpers
    # ----------------------------
    def _load_all(self) -> Dict[str, Any]:
        try:
            with open(META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"subchats": {}}

    def _save_all(self, data: Optional[Dict[str, Any]] = None) -> None:
        payload = data if data is not None else self._data
        payload.setdefault("subchats", {})
        self._data = payload
        _atomic_write(META_PATH, payload)

    def _get_subchat_meta(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get("subchats", {}).get(subchat_id)

    def _ensure_subchat_entry(self, subchat_id: str) -> Dict[str, Any]:
        subchats = self._data.setdefault("subchats", {})
        if subchat_id not in subchats:
            subchats[subchat_id] = {
                "owner": "",
                "label": "",
                "is_private": False,
                "allowed_agents": [],
                "password": None,
                "security_questions": [],
                "flags": {},
            }
        return subchats[subchat_id]

    def _audit_event(self, event: Dict[str, Any]):
        if self._audit:
            try:
                self._audit(event)
            except Exception:
                pass

    # ----------------------------
    # Subchat lifecycle / config
    # ----------------------------
    def create_or_update_subchat(
        self,
        subchat_id: str,
        owner: str,
        label: str,
        is_private: bool = False,
        allowed_agents: Optional[List[str]] = None,
        flags: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = self._ensure_subchat_entry(subchat_id)
        entry.update(
            {
                "owner": owner,
                "label": label,
                "is_private": bool(is_private),
                "allowed_agents": allowed_agents or [],
                "flags": flags or {},
            }
        )
        self._save_all()
        self._audit_event({"event": "subchat_created_or_updated", "subchat_id": subchat_id, "owner": owner})

    # ----------------------------
    # Password management
    # ----------------------------
    def set_password(self, subchat_id: str, password: str) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        meta["password"] = _hash_password(password)
        self._save_all()
        self._audit_event({"event": "set_password", "subchat_id": subchat_id})

    def clear_password(self, subchat_id: str) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        meta["password"] = None
        self._save_all()
        self._audit_event({"event": "clear_password", "subchat_id": subchat_id})

    def verify_password(self, subchat_id: str, password: str) -> bool:
        meta = self._get_subchat_meta(subchat_id)
        if not meta:
            return False
        pw = meta.get("password")
        if not pw:
            return False
        ok = _verify_password(password, pw.get("salt", ""), pw.get("dk", ""), pw.get("iterations", _PBKDF2_ITER))
        self._audit_event({"event": "verify_password", "subchat_id": subchat_id, "allowed": ok})
        return ok

    # ----------------------------
    # Allowed agents / flags
    # ----------------------------
    def set_allowed_agents(self, subchat_id: str, agents: List[str]) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        meta["allowed_agents"] = list(dict.fromkeys(agents))
        self._save_all()
        self._audit_event({"event": "set_allowed_agents", "subchat_id": subchat_id, "agents": agents})

    def add_allowed_agent(self, subchat_id: str, agent: str) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        if agent not in meta["allowed_agents"]:
            meta["allowed_agents"].append(agent)
            self._save_all()
        self._audit_event({"event": "add_allowed_agent", "subchat_id": subchat_id, "agent": agent})

    def remove_allowed_agent(self, subchat_id: str, agent: str) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        if agent in meta["allowed_agents"]:
            meta["allowed_agents"].remove(agent)
            self._save_all()
        self._audit_event({"event": "remove_allowed_agent", "subchat_id": subchat_id, "agent": agent})

    def set_flags(self, subchat_id: str, flags: Dict[str, Any]) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        meta["flags"] = dict(flags or {})
        self._save_all()
        self._audit_event({"event": "set_flags", "subchat_id": subchat_id})

    def update_flags(self, subchat_id: str, updates: Dict[str, Any]) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        meta.setdefault("flags", {}).update(updates or {})
        self._save_all()
        self._audit_event({"event": "update_flags", "subchat_id": subchat_id, "updates": updates})

    def get_flags(self, subchat_id: str) -> Dict[str, Any]:
        meta = self._get_subchat_meta(subchat_id)
        return dict(meta.get("flags", {})) if meta else {}

    # ----------------------------
    # Security questions
    # ----------------------------
    def set_security_questions(self, subchat_id: str, questions: List[Dict[str, str]]) -> None:
        meta = self._ensure_subchat_entry(subchat_id)
        stored: List[Dict[str, str]] = []
        for qa in questions:
            question = qa.get("question") or qa.get("q") or ""
            answer = qa.get("answer") or ""
            if not answer:
                raise ValueError("Security answers must be non-empty")
            answer_hash = hashlib.sha256(answer.strip().lower().encode("utf-8")).hexdigest()
            stored.append({"question": question, "answer_hash": answer_hash})
        meta["security_questions"] = stored
        self._save_all()
        self._audit_event({"event": "set_security_questions", "subchat_id": subchat_id})

    def verify_security_answer(self, subchat_id: str, question_index: int, answer: str) -> bool:
        meta = self._get_subchat_meta(subchat_id)
        if not meta:
            return False
        questions = meta.get("security_questions") or []
        if question_index < 0 or question_index >= len(questions):
            return False
        provided_hash = hashlib.sha256(answer.strip().lower().encode("utf-8")).hexdigest()
        ok = secrets.compare_digest(provided_hash, questions[question_index].get("answer_hash", ""))
        self._audit_event(
            {
                "event": "verify_security_answer",
                "subchat_id": subchat_id,
                "question_index": question_index,
                "allowed": ok,
            }
        )
        return ok

    # ----------------------------
    # Permissions & access checks
    # ----------------------------
    def _audit_access(self, subchat_id: str, actor_id: str, mode: str, allowed: bool):
        self._audit_event(
            {
                "event": "subchat_access_attempt",
                "subchat_id": subchat_id,
                "actor_id": actor_id,
                "mode": mode,
                "allowed": allowed,
            }
        )

    def can_read(self, subchat_id: str, actor_id: str, actor_role: str = "user") -> bool:
        meta = self._get_subchat_meta(subchat_id)
        if not meta:
            self._audit_access(subchat_id, actor_id, "read", False)
            return False
        if actor_role in {"master", "admin"}:
            self._audit_access(subchat_id, actor_id, "read", True)
            return True
        if actor_id == meta.get("owner"):
            self._audit_access(subchat_id, actor_id, "read", True)
            return True
        if meta.get("is_private"):
            allowed = actor_id in (meta.get("allowed_agents") or [])
            self._audit_access(subchat_id, actor_id, "read", allowed)
            return allowed
        self._audit_access(subchat_id, actor_id, "read", True)
        return True

    def can_write(self, subchat_id: str, actor_id: str, actor_role: str = "user") -> bool:
        meta = self._get_subchat_meta(subchat_id)
        if not meta:
            self._audit_access(subchat_id, actor_id, "write", False)
            return False
        if actor_role in {"master", "admin"}:
            self._audit_access(subchat_id, actor_id, "write", True)
            return True
        if actor_id == meta.get("owner"):
            self._audit_access(subchat_id, actor_id, "write", True)
            return True
        if meta.get("is_private"):
            allowed = actor_id in (meta.get("allowed_agents") or [])
        else:
            allowed = actor_id in (meta.get("allowed_agents") or [])
        self._audit_access(subchat_id, actor_id, "write", allowed)
        return allowed

    def can_admin(self, subchat_id: str, actor_id: str, actor_role: str = "user") -> bool:
        meta = self._get_subchat_meta(subchat_id)
        if not meta:
            self._audit_access(subchat_id, actor_id, "admin", False)
            return False
        allowed = actor_role in {"master", "admin"} or actor_id == meta.get("owner")
        self._audit_access(subchat_id, actor_id, "admin", allowed)
        return allowed

    # ----------------------------
    # Utility & inspection
    # ----------------------------
    def list_subchats(self) -> List[str]:
        return list(self._data.get("subchats", {}).keys())

    def get_subchat_info(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        meta = self._get_subchat_meta(subchat_id)
        return dict(meta) if meta else None


__all__ = ["SubchatSecurity"]
