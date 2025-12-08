"""Captain's Log Master Root mode manager (framework only).

This module provides a minimal, import-safe Captain's Log manager that wraps the
shared state object exposed by ``cl_state``. It intentionally avoids
implementing journaling, RAG, encryption, or any file I/O in this phase. The
purpose is to offer a stable API for the runtime and future subsystems while
remaining side-effect free.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any

from .cl_state import CaptainsLogState
from .cl_journal import JournalStore
from .cl_rag import CaptainsLogRAG


class CaptainsLogManager:
    """
    Controls Captain’s Log Master Root Mode and its private journal + RAG.

    Rules:
    - All journal and RAG operations require Captain’s Log mode to be active.
    - No journal text or RAG contents are exposed to other subsystems.
    - No automatic logging of sensitive content.
    """

    def __init__(self) -> None:
        # Mode state
        self.state = CaptainsLogState()

        # Private journal storage (on disk, JSONL)
        self.journal = JournalStore(Path("private/captains_log/journal.jsonl"))

        # Private in-memory RAG for Captain's Log
        self.rag = CaptainsLogRAG(self.state)

    # -------------------------------------------------
    # Mode control
    # -------------------------------------------------
    def enter(self) -> bool:
        self.state.enter()
        return True

    def exit(self) -> bool:
        self.state.exit()
        return True

    def is_active(self) -> bool:
        return bool(getattr(self.state, "active", False))

    def current_mode(self) -> str:
        return "captains_log" if self.is_active() else "normal"

    def get_status(self) -> Dict[str, Any]:
        """
        Minimal status used by bootup tests and diagnostics.
        Does NOT include any journal or RAG contents.
        """
        return {
            "status": "ok",
            "active": self.is_active(),
            "mode": self.current_mode(),
        }

    # -------------------------------------------------
    # Journal operations
    # -------------------------------------------------
    def _ensure_active(self) -> None:
        if not self.is_active():
            raise PermissionError("Captain’s Log operations require Captain’s Log mode to be active.")

    def add_journal_entry(self, text: str) -> Dict[str, Any]:
        """
        Add a new journal entry and ingest it into the private RAG memory.

        Returns the full entry dict (id, timestamp, mode, text).
        """
        self._ensure_active()
        entry_id = self.journal.add_entry(text, mode="master_root")

        # Fetch the new entry so we can mirror it into RAG.
        entries = self.journal.list_entries()
        entry: Dict[str, Any] | None = None
        for e in entries:
            if e.get("id") == entry_id:
                entry = e
                break

        if entry is not None:
            # Ingest into private Captain's Log RAG memory.
            self.rag.ingest_entry(entry)

        return entry or {"id": entry_id, "text": text, "mode": "master_root"}

    def list_journal_entries(self) -> List[Dict[str, Any]]:
        """
        List all journal entries (metadata + text).
        Only allowed in Captain’s Log mode.
        """
        self._ensure_active()
        return self.journal.list_entries()

    def clear_journal(self) -> None:
        """
        Clear ALL journal data and the associated RAG memory.
        Only allowed in Captain’s Log mode.
        """
        self._ensure_active()
        self.journal.clear()
        self.rag.clear()

    # -------------------------------------------------
    # RAG operations (private to Captain's Log)
    # -------------------------------------------------
    def search_rag(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search the Captain's Log private RAG memory.

        Phase 1: naive text search implemented by CaptainsLogRAG.
        """
        self._ensure_active()
        return self.rag.search(query, limit=limit)

    def rebuild_rag_from_journal(self) -> None:
        """
        Rebuild the private Captain's Log RAG memory from all journal entries.
        Useful if the in-memory RAG is reset or implementation changes.
        """
        self._ensure_active()
        entries = self.journal.list_entries()
        self.rag.clear()
        if entries:
            self.rag.bulk_ingest(entries)


# -------------------------------------------------
# Singleton accessor
# -------------------------------------------------
_manager: Optional[CaptainsLogManager] = None


def get_manager() -> CaptainsLogManager:
    global _manager
    if _manager is None:
        _manager = CaptainsLogManager()
    return _manager
