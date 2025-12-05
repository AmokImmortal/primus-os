"""
SubChat Memory Engine
Location: /core/subchat_memory.py

Simple, local, JSON-backed memory store for SubChats.
Each SubChat gets its own memory file under core/subchat_memories/<subchat_id>.json

Features:
- Add / update / delete memory entries
- Time-stamped entries with uuid ids
- Retrieve recent entries, query by keyword (simple substring)
- Export / import for backups
- Size limits (max_entries) to prevent uncontrolled growth
- Basic thread-safe file operations (OS-level atomic replace)
- Safe default paths inside core/subchat_memories
"""

from __future__ import annotations
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import tempfile

# Location for storing subchat memory files (core/subchat_memories)
CORE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = CORE_DIR / "subchat_memories"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class SubChatMemory:
    """
    Manages memory for a specific subchat.
    Each entry is a dict:
        {
            "id": <uuid str>,
            "timestamp": <ISO UTC str>,
            "content": <string>,
            "metadata": { ... }  # optional
        }
    """

    def __init__(self, subchat_id: str, max_entries: int = 1000):
        self.subchat_id = str(subchat_id)
        self.max_entries = int(max_entries)
        self.file_path = MEMORY_DIR / f"{self.subchat_id}.json"
        self._entries: List[Dict[str, Any]] = []
        self._load()

    # -------------------------
    # Persistence
    # -------------------------
    def _load(self) -> None:
        if not self.file_path.exists():
            self._entries = []
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, list):
                self._entries = obj
            else:
                # backwards compatibility: some files might be dicts
                self._entries = obj.get("entries", [])
        except Exception:
            # if anything goes wrong, do not crash the caller; start fresh
            self._entries = []

    def _atomic_write(self, data: Any) -> None:
        """
        Write file atomically to avoid corruption (write to temp then move).
        """
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="mem_", dir=str(MEMORY_DIR))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmpf:
                json.dump(data, tmpf, ensure_ascii=False, indent=2)
                tmpf.flush()
                os.fsync(tmpf.fileno())
            os.replace(tmp_path, str(self.file_path))
        finally:
            # cleanup if something went wrong and tmp still exists
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _save(self) -> None:
        # Enforce max_entries before saving
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            # drop oldest entries
            self._entries = self._entries[-self.max_entries :]
        try:
            self._atomic_write(self._entries)
        except Exception:
            # best-effort save; ignore failures to avoid crashes
            pass

    # -------------------------
    # CRUD operations
    # -------------------------
    def add_entry(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Add a new memory entry.
        Returns the created entry.
        """
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "content": str(content),
            "metadata": metadata or {},
        }
        self._entries.append(entry)
        # enforce size limit immediately
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]
        self._save()
        return entry

    def update_entry(self, entry_id: str, content: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update an existing entry by id. Returns True if updated.
        """
        for e in self._entries:
            if e.get("id") == entry_id:
                if content is not None:
                    e["content"] = str(content)
                if metadata is not None:
                    e["metadata"] = metadata
                e["timestamp"] = _now_iso()
                self._save()
                return True
        return False

    def delete_entry(self, entry_id: str) -> bool:
        """
        Delete an entry by id. Returns True if deleted.
        """
        orig_len = len(self._entries)
        self._entries = [e for e in self._entries if e.get("id") != entry_id]
        if len(self._entries) != orig_len:
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all memory entries for this subchat."""
        self._entries = []
        try:
            if self.file_path.exists():
                self.file_path.unlink()
        except Exception:
            pass

    # -------------------------
    # Retrieval / Query
    # -------------------------
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent `limit` entries (newest first)."""
        if limit <= 0:
            return []
        return list(reversed(self._entries[-limit:]))

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all entries in insertion order (oldest first)."""
        return list(self._entries)

    def query(self, keyword: str, limit: int = 10, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Simple keyword query over content and metadata values.
        Returns up to `limit` matching entries, ordered newest-first.
        """
        if not keyword:
            return []
        kw = keyword if case_sensitive else keyword.lower()
        matches: List[Dict[str, Any]] = []
        for e in reversed(self._entries):  # newest-first
            hay = e.get("content", "")
            hay_cmp = hay if case_sensitive else hay.lower()
            if kw in hay_cmp:
                matches.append(e)
                if len(matches) >= limit:
                    break
            else:
                # check metadata values
                meta = e.get("metadata", {})
                found = False
                for v in meta.values():
                    try:
                        s = str(v)
                        s_cmp = s if case_sensitive else s.lower()
                        if kw in s_cmp:
                            found = True
                            break
                    except Exception:
                        continue
                if found:
                    matches.append(e)
                    if len(matches) >= limit:
                        break
        return matches

    # -------------------------
    # Export / Import / Info
    # -------------------------
    def export_json(self, dest_path: Optional[str] = None) -> str:
        """
        Export memory to JSON file. If dest_path is None, creates a timestamped export in MEMORY_DIR.
        Returns path to exported file.
        """
        dest = Path(dest_path) if dest_path else MEMORY_DIR / f"{self.subchat_id}_export_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        try:
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
            return str(dest)
        except Exception as e:
            raise RuntimeError(f"Export failed: {e}")

    def import_json(self, src_path: str, merge: bool = True) -> Dict[str, Any]:
        """
        Import entries from a JSON file. If merge is False, existing entries are replaced.
        Returns summary dict.
        """
        src = Path(src_path)
        if not src.exists():
            return {"status": "error", "message": "source_not_found"}
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return {"status": "error", "message": "invalid_format"}
            if merge:
                # naive merge: append new entries (no dedupe)
                self._entries.extend(data)
            else:
                self._entries = data
            # enforce max entries
            if self.max_entries is not None and len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries :]
            self._save()
            return {"status": "ok", "imported": len(data)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def info(self) -> Dict[str, Any]:
        """Return basic info about this subchat memory."""
        return {
            "subchat_id": self.subchat_id,
            "path": str(self.file_path),
            "entries": len(self._entries),
            "max_entries": self.max_entries,
            "last_timestamp": self._entries[-1]["timestamp"] if self._entries else None,
        }