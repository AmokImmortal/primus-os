"""
core/session_manager.py

Lightweight session history manager for PRIMUS OS.

- Stores chat/session turns on disk under a given root directory.
- No background threads, no network access.
- Designed to be safely constructed by PrimusCore with:

    SessionManager(session_root=os.path.join(system_root, "sessions"))

API (stable surface for PrimusCore / CLI usage):

    class SessionManager:
        def __init__(self, session_root: str | Path, max_history: int = 100): ...

        def create_session(self, session_id: str | None = None) -> str: ...
        def list_sessions(self) -> list[str]: ...
        def session_exists(self, session_id: str) -> bool: ...

        def save_turn(self, session_id: str, role: str, content: str) -> None: ...
        def load_history(
            self,
            session_id: str,
            limit: int | None = None,
        ) -> list[dict[str, str]]: ...

        def delete_session(self, session_id: str) -> bool: ...

    get_session_manager(session_root: str | Path | None = None) -> SessionManager
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionManager:
    """
    Disk-backed session manager.

    Storage layout (inside `session_root`):

        sessions/
            <session_id>.jsonl   # one JSON object per line:
                                 #   {
                                 #       "ts": float,
                                 #       "role": "user" | "assistant" | ...,
                                 #       "content": str
                                 #   }
    """

    def __init__(self, session_root: str | Path, max_history: int = 100) -> None:
        self.session_root = Path(session_root)
        self.max_history = max_history

        # Directory where all sessions live
        self.sessions_dir = self.session_root
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Session identifiers / paths
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self.sessions_dir / f"{safe_id}.jsonl"

    def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new session.

        If no session_id is provided, a UUID4 is generated.
        Returns the session_id.
        """
        if session_id is None:
            session_id = uuid.uuid4().hex

        path = self._session_path(session_id)
        if not path.exists():
            # Touch the file so it exists, but keep it empty initially
            path.touch()

        return session_id

    def session_exists(self, session_id: str) -> bool:
        return self._session_path(session_id).exists()

    def list_sessions(self) -> List[str]:
        """
        Return a list of known session IDs (based on files in sessions_dir).
        """
        ids: List[str] = []
        for p in self.sessions_dir.glob("*.jsonl"):
            ids.append(p.stem)
        return sorted(ids)

    # ------------------------------------------------------------------
    # History storage
    # ------------------------------------------------------------------

    def save_turn(self, session_id: str, role: str, content: str) -> None:
        """
        Append a single turn to the session history.

        No background activity; simple append-only write.
        """
        if not self.session_exists(session_id):
            self.create_session(session_id)

        path = self._session_path(session_id)
        record: Dict[str, Any] = {
            "ts": time.time(),
            "role": role,
            "content": content,
        }

        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Optional: enforce max_history by trimming oldest entries
        if self.max_history > 0:
            self._trim_history(path)

    def _trim_history(self, path: Path) -> None:
        """
        Keep at most `max_history` lines in the JSONL file.
        If max_history <= 0, no trimming is performed.
        """
        if self.max_history <= 0 or not path.exists():
            return

        try:
            with path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return

        if len(lines) <= self.max_history:
            return

        # Keep only the last max_history lines
        lines = lines[-self.max_history :]

        try:
            with path.open("w", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            # If trimming fails, we silently ignore; history remains larger.
            return

    def load_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Load the session history as a list of records:
            { "ts": float, "role": str, "content": str }

        If `limit` is provided, returns only the most recent `limit` turns.
        """
        path = self._session_path(session_id)
        if not path.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            records.append(obj)
                    except json.JSONDecodeError:
                        # Skip corrupted lines silently.
                        continue
        except OSError:
            return []

        if limit is not None and limit > 0:
            return records[-limit:]

        return records

    # ------------------------------------------------------------------
    # Destructive operations
    # ------------------------------------------------------------------

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session file from disk.
        Returns True if a file was removed, False otherwise.
        """
        path = self._session_path(session_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False


# ----------------------------------------------------------------------
# Singleton-style accessor (optional, but convenient)
# ----------------------------------------------------------------------

_global_session_manager: Optional[SessionManager] = None


def get_session_manager(session_root: Optional[str | Path] = None) -> SessionManager:
    """
    Return a process-global SessionManager instance.

    If not yet created, a new one is initialized. If `session_root` is not
    provided on first call, it defaults to "./sessions" relative to CWD.
    """
    global _global_session_manager

    if _global_session_manager is None:
        if session_root is None:
            session_root = Path.cwd() / "sessions"
        _global_session_manager = SessionManager(session_root=session_root)

    return _global_session_manager