"""Captain's Log RAG subsystem (Phase 1 skeleton).

This module defines a private, Captain's Log-only Retrieval-Augmented Generation
scaffold. It intentionally performs no real embedding or vector operations yet;
instead, it provides a minimal surface API and in-memory placeholders that will
be expanded in later phases. All operations are restricted to Captain's Log
Master Root Mode and must remain private to that context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any
from .cl_state import CaptainsLogState


@dataclass
class CaptainsLogRAG:
    """
    Phase 1 skeleton for Captain's Log RAG.

    - Completely private to Captain's Log.
    - No external storage, no vectors, no external services.
    - In-memory only for now.
    - All methods require Captain's Log mode to be active.
    """

    state: CaptainsLogState
    _entries: List[Dict[str, Any]] = field(default_factory=list)

    # -------------------------------------------------
    # Internal helpers
    # -------------------------------------------------
    def _ensure_active(self) -> None:
        if not self.state.active:
            raise PermissionError("Captain's Log RAG operations require Captain's Log mode to be active.")

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------
    def ingest_entry(self, entry: Dict[str, Any]) -> None:
        """
        Ingest a single journal-like entry into the Captain's Log RAG memory.

        `entry` is expected to be a dict with keys like:
        - id
        - timestamp
        - mode
        - text
        """
        self._ensure_active()
        # For now, just keep the entire entry in memory.
        self._entries.append(entry)

    def bulk_ingest(self, entries: List[Dict[str, Any]]) -> None:
        """
        Ingest multiple entries at once.
        """
        self._ensure_active()
        for e in entries:
            self._entries.append(e)

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Very naive Phase 1 search: case-insensitive substring match on `text`.

        Returns a list of entries (shallow copies) that match.
        """
        self._ensure_active()
        q = (query or "").strip().lower()
        if not q:
            return []

        results: List[Dict[str, Any]] = []
        for e in self._entries:
            text = str(e.get("text", "")).lower()
            if q in text:
                results.append(dict(e))
                if len(results) >= limit:
                    break
        return results

    def clear(self) -> None:
        """
        Clear all in-memory Captain's Log RAG entries.
        """
        self._ensure_active()
        self._entries.clear()