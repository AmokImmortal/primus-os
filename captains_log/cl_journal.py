"""Captain's Log journal subsystem (private, offline-only).

This module manages the Captain's Log journal entries in a local JSONL file. It
is intentionally self-contained and does not depend on other PRIMUS systems.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


class CaptainLogJournal:
    """Private journal for Captain's Log Master Root Mode.

    Entries are stored in JSONL format at ``captains_log/storage/journal.jsonl``.
    This class is side-effect free beyond file I/O and performs no external
    logging. No other subsystem should access this file.
    """

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        base_dir = storage_dir or os.path.join(os.path.dirname(__file__), "storage")
        self.storage_dir = base_dir
        self.journal_path = os.path.join(self.storage_dir, "journal.jsonl")
        self._lock = threading.Lock()
        self._current_mode = "root"

    def _ensure_storage_dir(self) -> None:
        os.makedirs(self.storage_dir, exist_ok=True)

    def _load_entries(self) -> List[Dict[str, object]]:
        if not os.path.exists(self.journal_path):
            return []
        entries: List[Dict[str, object]] = []
        with open(self.journal_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def add_entry(self, text: str, mode: str = "root") -> Dict[str, object]:
        if mode not in ("root", "user"):
            raise ValueError("mode must be 'root' or 'user'")
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = {
            "timestamp": timestamp,
            "entry_id": str(uuid.uuid4()),
            "mode": mode,
            "text": text,
        }
        payload = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self._ensure_storage_dir()
            with open(self.journal_path, "a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
            self._current_mode = mode
        return entry

    def list_entries(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        entries = self._load_entries()
        metadata = [
            {"timestamp": e.get("timestamp"), "entry_id": e.get("entry_id"), "mode": e.get("mode")}
            for e in entries
        ]
        if limit is not None and limit >= 0:
            metadata = metadata[-limit:]
        return metadata

    def read_entry(self, entry_id: str) -> Optional[Dict[str, object]]:
        entries = self._load_entries()
        for entry in entries:
            if entry.get("entry_id") == entry_id:
                return entry
        return None

    def clear_all(self) -> None:
        with self._lock:
            if self._current_mode != "root":
                raise PermissionError("Clearing the journal requires Captain's Log Master Root Mode.")
            if os.path.exists(self.journal_path):
                with open(self.journal_path, "w", encoding="utf-8"):
                    pass


__all__ = ["CaptainLogJournal"]
