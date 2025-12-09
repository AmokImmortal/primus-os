# core/session_manager.py
"""
Session Manager for PRIMUS OS

This module provides persistent, per-session chat history storage. Histories are
stored on disk so that conversations survive across CLI invocations. Each
session is saved as a JSON file containing a list of message dictionaries with
``role`` and ``content`` keys (and optional ``ts`` metadata).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_DIR = Path("system") / "sessions"
DEFAULT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Shared lock to keep disk writes safe across threads/processes
_io_lock = threading.Lock()


def _now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"


class SessionManager:
    """Manage chat sessions with simple JSON persistence."""

    def __init__(self, session_root: Optional[str | Path] = None, max_history: int = 500):
        root = Path(session_root) if session_root is not None else Path("system")
        self.session_root: Path = root
        self.sessions_dir: Path = (root / "sessions").resolve()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.max_history = max_history

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _session_path(self, session_id: str) -> Path:
        path = self.sessions_dir / f"{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _trim_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.max_history and len(messages) > self.max_history:
            return messages[-self.max_history :]
        return messages

    @staticmethod
    def _normalize_messages(raw: Any, session_id: str) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                role = item.get("role") or item.get("who")
                content = item.get("content")
                if content is None:
                    content = item.get("text")
                if role and content is not None:
                    entry = {"role": role, "content": content}
                    if "ts" in item:
                        entry["ts"] = item.get("ts")
                    messages.append(entry)
        elif isinstance(raw, dict):
            # Some older formats wrap messages inside a dict
            nested = raw.get("messages", [])
            messages = SessionManager._normalize_messages(nested, session_id)
        else:
            logger.warning(
                "SessionManager: unsupported session payload for %s; returning empty history", session_id
            )
        return messages

    def _read_session_file(self, session_id: str) -> List[Dict[str, Any]]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return self._normalize_messages(raw, session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SessionManager.load_history: failed to parse %s: %s", path, exc)
            return []

    def _write_session_file(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        path = self._session_path(session_id)
        payload: Dict[str, Any] = {
            "id": session_id,
            "created_at": _now_iso(),
            "messages": messages,
        }
        tmp_path = path.with_suffix(".json.tmp")
        try:
            with _io_lock:
                with tmp_path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                tmp_path.replace(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SessionManager: failed to write %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Return stored history for a session, or an empty list if missing."""
        history = self._read_session_file(session_id)
        if history:
            logger.debug("SessionManager.load_history: loaded %d messages for %s", len(history), session_id)
        return history

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Compatibility wrapper that delegates to ``load_history``."""
        try:
            history = self.load_history(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("load_session failed for %r: %s", session_id, exc)
            return []
        return history or []

    def append_message(self, session_id: str, msg: Dict[str, Any]) -> None:
        """Append a message and persist the session, trimming if needed."""
        if not isinstance(msg, dict):
            logger.debug("SessionManager.append_message: msg must be dict; skipping for %s", session_id)
            return

        role = msg.get("role")
        content = msg.get("content")
        if role is None or content is None:
            logger.debug("SessionManager.append_message: incomplete message for %s; skipping", session_id)
            return

        history = self.load_session(session_id)
        entry = {"role": role, "content": content}
        if "ts" in msg:
            entry["ts"] = msg.get("ts")
        else:
            entry["ts"] = _now_iso()

        history.append(entry)
        history = self._trim_history(history)
        try:
            self._write_session_file(session_id, history)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SessionManager.append_message failed for %r: %s", session_id, exc)
            return
        logger.debug(
            "SessionManager.append_message: session=%s total_messages=%d", session_id, len(history)
        )

    def save_history(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        messages = self._trim_history(messages)
        self._write_session_file(session_id, messages)

    def delete_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        try:
            if path.exists():
                path.unlink()
                logger.info("SessionManager.delete_session: removed %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SessionManager.delete_session: failed to delete %s: %s", path, exc)

    def list_sessions(self) -> List[str]:
        sessions = []
        if not self.sessions_dir.exists():
            return sessions
        for path in self.sessions_dir.glob("*.json"):
            sessions.append(path.stem)
        return sorted(sessions)

    def session_exists(self, session_id: str) -> bool:
        return self._session_path(session_id).exists()

    # ------------------------------------------------------------------
    # Legacy/compat helpers (lightweight stubs retained for compatibility)
    # ------------------------------------------------------------------
    def ensure_session(self, session_id: str, owner: str = "user", privacy: str = "private") -> Dict[str, Any]:
        # owner and privacy currently informational only
        if not self.session_exists(session_id):
            self._write_session_file(session_id, [])
        return {"id": session_id, "owner": owner, "privacy": privacy, "messages": []}

    def create_session(
        self,
        title: str,
        owner: str = "user",
        privacy: str = "private",
        meta: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = session_id or title
        self._write_session_file(sid, [])
        return {
            "id": sid,
            "title": title,
            "owner": owner,
            "privacy": privacy,
            "meta": meta or {},
            "messages": [],
        }

    def add_message(
        self,
        session_id: str,
        role: str,
        who: str,
        text: str,
        ts: Optional[str] = None,
        allow_agent_read_cross: bool = True,
    ) -> Dict[str, Any]:
        msg = {"role": role, "content": text, "ts": ts or _now_iso(), "who": who}
        self.append_message(session_id, msg)
        return msg

    def get_messages(self, session_id: str, start: int = 0, end: Optional[int] = None) -> List[Dict[str, Any]]:
        history = self.load_history(session_id)
        return history[start:end]

    def clear_all_sessions(self) -> None:
        for sid in self.list_sessions():
            self.delete_session(sid)


# Single global manager
session_manager = SessionManager()

