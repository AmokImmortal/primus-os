"""
SubChat Session Manager
Location: C:\P.R.I.M.U.S OS\System\core\subchat_session_manager.py

Responsibilities:
- Track active and archived subchat sessions
- Session lifecycle: create, update, close
- Ownership, privacy (password-protected private sessions), metadata
- Message append and retrieval (keeps light in-memory cache, persisted to disk)
- Thread-safe operations and safe persistent storage (JSON)
"""

from __future__ import annotations
import json
import hashlib
import secrets
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Resolve paths relative to core folder
CORE_DIR = Path(__file__).resolve().parents[0]
SYSTEM_ROOT = CORE_DIR.parents[0]
DATA_DIR = CORE_DIR / "subchat_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_PATH = DATA_DIR / "subchat_sessions.json"

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(pw: str, salt: Optional[str] = None) -> Dict[str, str]:
    """Return dict with salt and hex digest of (salt + pw)."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256()
    h.update((salt + pw).encode("utf-8"))
    return {"salt": salt, "digest": h.hexdigest()}


class SubChatSessionManager:
    """
    Thread-safe manager for subchat sessions.
    Sessions are persisted to SESSIONS_PATH as JSON.
    """

    def __init__(self, persist_path: Path = SESSIONS_PATH):
        self._persist_path = persist_path
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load()

    # -------------------------
    # Persistence
    # -------------------------
    def _load(self) -> None:
        with _LOCK:
            if self._persist_path.exists():
                try:
                    with open(self._persist_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._sessions = data
                    else:
                        self._sessions = {}
                except Exception:
                    # If load fails, start with empty sessions but do not raise
                    self._sessions = {}
            else:
                self._sessions = {}

    def _save(self) -> None:
        with _LOCK:
            tmp = self._persist_path.with_suffix(".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._sessions, f, indent=2, ensure_ascii=False)
                tmp.replace(self._persist_path)
            except Exception:
                # Best-effort save; on failure do nothing (avoids crashing manager)
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    # -------------------------
    # Session lifecycle
    # -------------------------
    def create_session(
        self,
        name: str,
        owner: str,
        private: bool = False,
        password: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create new session and return session dict.
        If private=True and password provided, password is stored hashed.
        """
        with _LOCK:
            sid = secrets.token_hex(12)
            now = _now_iso()
            pwd_entry = None
            if private and password:
                pwd_entry = _hash_password(password)
            session = {
                "id": sid,
                "name": name,
                "owner": owner,
                "created_at": now,
                "updated_at": now,
                "active": True,
                "private": bool(private),
                "password": pwd_entry,  # {"salt":..., "digest":...} or None
                "messages": [],  # list of {"ts":..., "sender":..., "content":...}
                "metadata": metadata or {},
            }
            self._sessions[sid] = session
            self._save()
            return session

    def get_session(self, session_id: str, require_private_access: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Return session dict or None.
        If session is private and require_private_access provided (the password),
        it will validate it; otherwise private sessions return limited info.
        """
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return None
            if s.get("private"):
                if require_private_access is None:
                    # Return a sanitized view (no messages or password)
                    sanitized = {k: v for k, v in s.items() if k not in ("messages", "password")}
                    sanitized["messages"] = []  # hide messages
                    return sanitized
                else:
                    if self._verify_password_entry(s.get("password"), require_private_access):
                        return s
                    else:
                        return None
            return s

    def list_sessions(self, include_private: bool = False, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return list of session summaries.
        By default private sessions are excluded unless include_private=True.
        If owner provided, filter by owner.
        """
        with _LOCK:
            out = []
            for s in self._sessions.values():
                if s.get("private") and not include_private:
                    continue
                if owner and s.get("owner") != owner:
                    continue
                # Return summary (no full messages)
                summary = {
                    "id": s["id"],
                    "name": s["name"],
                    "owner": s["owner"],
                    "created_at": s["created_at"],
                    "updated_at": s["updated_at"],
                    "active": s["active"],
                    "private": s["private"],
                    "metadata": s.get("metadata", {}),
                }
                out.append(summary)
            return out

    def close_session(self, session_id: str) -> bool:
        """Mark session inactive. Returns True if existed and was closed."""
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            s["active"] = False
            s["updated_at"] = _now_iso()
            self._save()
            return True

    def reopen_session(self, session_id: str) -> bool:
        """Re-open a closed session."""
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            s["active"] = True
            s["updated_at"] = _now_iso()
            self._save()
            return True

    # -------------------------
    # Messages
    # -------------------------
    def add_message(self, session_id: str, sender: str, content: str) -> bool:
        """
        Append message to session. Returns True on success.
        Message stored as {"ts", "sender", "content"}.
        """
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            msg = {"ts": _now_iso(), "sender": sender, "content": content}
            s.setdefault("messages", []).append(msg)
            s["updated_at"] = _now_iso()
            # Keep only recent N messages in memory? For now persist everything.
            self._save()
            return True

    def get_messages(self, session_id: str, limit: Optional[int] = None, require_private_access: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Return messages for a session.
        For private sessions, a valid password (require_private_access) is required.
        If limit provided, return last `limit` messages.
        """
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return None
            if s.get("private"):
                if not self._verify_password_entry(s.get("password"), require_private_access):
                    return None
            msgs = s.get("messages", [])
            if limit is not None:
                return msgs[-limit:]
            return msgs

    # -------------------------
    # Password management
    # -------------------------
    def set_password(self, session_id: str, new_password: str) -> bool:
        """
        Set or replace password on a session. Enables private mode.
        """
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            s["password"] = _hash_password(new_password)
            s["private"] = True
            s["updated_at"] = _now_iso()
            self._save()
            return True

    def clear_password(self, session_id: str, verify_password: Optional[str] = None) -> bool:
        """
        Remove password and make session non-private (requires verifying current password).
        If verify_password is None and session is private, fail.
        """
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            if s.get("private"):
                if verify_password is None:
                    return False
                if not self._verify_password_entry(s.get("password"), verify_password):
                    return False
            s["password"] = None
            s["private"] = False
            s["updated_at"] = _now_iso()
            self._save()
            return True

    def _verify_password_entry(self, entry: Optional[Dict[str, str]], candidate: Optional[str]) -> bool:
        """Verify password entry object against provided candidate password."""
        if not entry or not candidate:
            return False
        salt = entry.get("salt")
        expected = entry.get("digest")
        if not salt or not expected:
            return False
        h = hashlib.sha256()
        h.update((salt + candidate).encode("utf-8"))
        return h.hexdigest() == expected

    # -------------------------
    # Utilities
    # -------------------------
    def update_metadata(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        """Merge/update metadata for a session."""
        with _LOCK:
            s = self._sessions.get(session_id)
            if not s:
                return False
            m = s.get("metadata", {})
            m.update(metadata)
            s["metadata"] = m
            s["updated_at"] = _now_iso()
            self._save()
            return True

    def delete_session(self, session_id: str) -> bool:
        """Remove session entirely. Use with caution."""
        with _LOCK:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._save()
                return True
            return False

    def count(self) -> int:
        with _LOCK:
            return len(self._sessions)

    # Expose internal state (careful: returning copy)
    def dump_all(self) -> Dict[str, Any]:
        with _LOCK:
            return json.loads(json.dumps(self._sessions))