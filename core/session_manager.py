# core/session_manager.py
"""
Session Manager for PRIMUS OS

Responsibilities:
- Create / list / load / save chat sessions (PRIMUS main + agent sub-sessions)
- Support private vs shared sessions
- Persist sessions to disk under system/sessions/
- Provide simple APIs to append messages, query history, export transcripts
- Enforce permissions using the personality manager where applicable
- Lightweight locking/atomic save to reduce corruption risk

Storage layout (relative to repo root):
system/
  sessions/
    <session_id>.json

Session structure (example):
{
  "id": "session-uuid",
  "title": "PRIMUS — Business Ops",
  "created_at": "2025-11-30T12:00:00Z",
  "owner": "user",                 # "user" or agent name
  "privacy": "private" | "shared",
  "agents_linked": ["BusinessAgent"],
  "messages": [
      {"role":"user","who":"you","text":"Hello", "ts": "..."},
      {"role":"agent","who":"PRIMUS","text":"Hi", "ts":"..."}
  ],
  "meta": { ... }   # optional metadata
}
"""

import os
import json
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

# Import personality manager for permission checks (assumes core/persona.py loaded earlier)
try:
    from core.persona import personality_manager
except Exception:
    # If running standalone tests, a minimal stub is used
    personality_manager = None  # type: ignore

# Path for sessions folder
SESSIONS_DIR = os.path.join("system", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Simple thread lock for safe writes
_io_lock = threading.Lock()


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def _session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


class SessionNotFound(Exception):
    pass


class PermissionDenied(Exception):
    pass


class SessionManager:
    def __init__(self):
        # in-memory cache for quick lookups (id -> dict)
        self._cache: Dict[str, Dict[str, Any]] = {}
        # load existing session metadata (lazy loads content)
        self._index_sessions()

    # -------------------------
    # Disk index / bootstrap
    # -------------------------
    def _index_sessions(self):
        self._cache = {}
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            sid = fname[:-5]
            # don't load entire content now; store basic metadata placeholder
            try:
                with open(_session_path(sid), "r", encoding="utf-8") as f:
                    obj = json.load(f)
                # Minimal validation
                if isinstance(obj, dict) and obj.get("id") == sid:
                    self._cache[sid] = obj
            except Exception:
                # ignore malformed files; they can be inspected later
                continue

    # -------------------------
    # Create / Save / Load
    # -------------------------
    def create_session(self, title: str, owner: str = "user", privacy: str = "private", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "title": title,
            "created_at": _now_iso(),
            "owner": owner,
            "privacy": privacy,  # "private" or "shared"
            "agents_linked": [],
            "messages": [],
            "meta": meta or {}
        }
        self._save_to_disk(session)
        self._cache[session_id] = session
        return session

    def _save_to_disk(self, session: Dict[str, Any]):
        path = _session_path(session["id"])
        tmp = path + ".tmp"
        with _io_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)
            # atomic replace
            os.replace(tmp, path)

    def save_session(self, session_id: str):
        session = self._cache.get(session_id)
        if not session:
            raise SessionNotFound(f"No session: {session_id}")
        self._save_to_disk(session)

    def load_session(self, session_id: str) -> Dict[str, Any]:
        # If cached, return it
        if session_id in self._cache:
            return self._cache[session_id]

        path = _session_path(session_id)
        if not os.path.exists(path):
            raise SessionNotFound(session_id)
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        self._cache[session_id] = obj
        return obj

    # -------------------------
    # Listing / Searching
    # -------------------------
    def list_sessions(self) -> List[Dict[str, Any]]:
        # Return light-weight session listings (id, title, owner, privacy, created_at)
        out = []
        for sid, obj in self._cache.items():
            out.append({
                "id": sid,
                "title": obj.get("title"),
                "owner": obj.get("owner"),
                "privacy": obj.get("privacy"),
                "created_at": obj.get("created_at")
            })
        return sorted(out, key=lambda x: x["created_at"])

    # -------------------------
    # Messages API
    # -------------------------
    def add_message(self, session_id: str, role: str, who: str, text: str, ts: Optional[str] = None, allow_agent_read_cross: bool = True) -> Dict[str, Any]:
        """
        role: "user" | "agent" | "system"
        who: identifier (e.g., "user", "PRIMUS", "BusinessAgent")
        """
        session = self.load_session(session_id)

        # Privacy enforcement: if session is private and message is from agent not owner,
        # check agent's permission to write into private sessions.
        if session.get("privacy") == "private" and who != session.get("owner"):
            if personality_manager:
                # if agent, ensure permission to write to private session
                if who != "user" and not personality_manager.allow_agent_write_other_agents(who):
                    raise PermissionDenied(f"Agent {who} not allowed to write to private session {session_id}")

        msg = {
            "role": role,
            "who": who,
            "text": text,
            "ts": ts or _now_iso()
        }
        session.setdefault("messages", []).append(msg)
        # persist immediately
        self._save_to_disk(session)
        return msg

    def get_messages(self, session_id: str, start: int = 0, end: Optional[int] = None) -> List[Dict[str, Any]]:
        session = self.load_session(session_id)
        msgs = session.get("messages", [])
        return msgs[start:end]

    # -------------------------
    # Sub-sessions / Agent linking
    # -------------------------
    def create_subsession(self, parent_session_id: str, title: str, agent_name: str, privacy: Optional[str] = None) -> Dict[str, Any]:
        parent = self.load_session(parent_session_id)
        # subsessions are owned by the same owner by default
        owner = parent.get("owner", "user")
        privacy = privacy or parent.get("privacy", "private")
        sub = self.create_session(title=title, owner=owner, privacy=privacy)
        # Link agent information
        sub.setdefault("agents_linked", []).append(agent_name)
        self._cache[sub["id"]] = sub
        # persist parent link
        parent.setdefault("meta", {}).setdefault("subsessions", []).append(sub["id"])
        self._save_to_disk(parent)
        return sub

    def link_agent_to_session(self, session_id: str, agent_name: str):
        session = self.load_session(session_id)
        if agent_name not in session.get("agents_linked", []):
            session.setdefault("agents_linked", []).append(agent_name)
            self._save_to_disk(session)

    # -------------------------
    # Privacy / permission helpers
    # -------------------------
    def set_privacy(self, session_id: str, privacy: str):
        if privacy not in ("private", "shared"):
            raise ValueError("privacy must be 'private' or 'shared'")
        session = self.load_session(session_id)
        session["privacy"] = privacy
        self._save_to_disk(session)

    def can_agent_read_session(self, agent_name: str, session_id: str) -> bool:
        session = self.load_session(session_id)
        if session.get("privacy") == "shared":
            return True
        # private session: only owner and permitted agents
        if agent_name == session.get("owner"):
            return True
        if personality_manager:
            return personality_manager.allow_agent_read_other_agents(agent_name)
        return False

    # -------------------------
    # Export / Transcript
    # -------------------------
    def export_transcript_txt(self, session_id: str, out_path: Optional[str] = None) -> str:
        session = self.load_session(session_id)
        lines = []
        lines.append(f"Session: {session.get('title')} ({session.get('id')})")
        lines.append(f"Owner: {session.get('owner')}")
        lines.append(f"Privacy: {session.get('privacy')}")
        lines.append(f"Created: {session.get('created_at')}")
        lines.append("\n--- Messages ---\n")
        for m in session.get("messages", []):
            ts = m.get("ts", "")
            who = m.get("who", "")
            role = m.get("role", "")
            text = m.get("text", "")
            lines.append(f"[{ts}] {who} ({role}):")
            lines.append(text)
            lines.append("")

        out_path = out_path or os.path.join(SESSIONS_DIR, f"{session_id}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return out_path

    # -------------------------
    # Administrative
    # -------------------------
    def delete_session(self, session_id: str):
        session = self._cache.get(session_id)
        if session:
            try:
                os.remove(_session_path(session_id))
            except FileNotFoundError:
                pass
            del self._cache[session_id]

    def clear_all_sessions(self):
        # Dangerous: deletes all on disk and in cache
        for sid in list(self._cache.keys()):
            try:
                os.remove(_session_path(sid))
            except Exception:
                pass
            del self._cache[sid]


# Single global manager
session_manager = SessionManager()