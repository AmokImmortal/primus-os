"""Captain's Log RAG subsystem (Phase 1 skeleton).

This module defines a private, Captain's Log-only Retrieval-Augmented Generation
scaffold. It intentionally performs no real embedding or vector operations yet;
instead, it provides a minimal surface API and in-memory placeholders that will
be expanded in later phases. All operations are restricted to Captain's Log
Master Root Mode and must remain private to that context.
"""

from __future__ import annotations

from typing import Dict, List

try:
    # Prefer the System namespace when available to match runtime imports.
    from System.captains_log import cl_state
except Exception:  # pragma: no cover - fallback for alternative layouts
    from captains_log import cl_state


class CaptainsLogRAG:
    """Private RAG placeholder for Captain's Log content.

    All public methods enforce Captain's Log Master Root Mode and avoid any
    logging or external side effects. Data is kept in-memory for Phase 1.
    """

    def __init__(self) -> None:
        self._entries: List[Dict[str, object]] = []

    def _ensure_active(self) -> None:
        if not cl_state.is_captains_log_mode():
            raise PermissionError(
                "Captain's Log RAG is only available when Captain's Log mode is active."
            )

    def ingest_entry(self, entry: Dict[str, object]) -> None:
        """Ingest a single journal entry into the Captain's Log RAG."""

        self._ensure_active()
        if not isinstance(entry, dict):
            raise TypeError("entry must be a dictionary")
        self._entries.append(entry)

    def bulk_ingest(self, entries: List[Dict[str, object]]) -> None:
        """Ingest multiple journal entries at once."""

        self._ensure_active()
        if entries is None:
            raise TypeError("entries must be a list of dictionaries")
        for entry in entries:
            self.ingest_entry(entry)

    def search(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        """Search the Captain's Log RAG by naive substring matching (placeholder)."""

        self._ensure_active()
        if not query:
            return []

        lowered = query.lower()
        results: List[Dict[str, object]] = []
        for entry in reversed(self._entries):
            # Do not log or expose text beyond the return value.
            if any(
                isinstance(value, str) and lowered in value.lower()
                for value in entry.values()
            ):
                results.append(entry)
            if len(results) >= limit:
                break
        return results

    def clear(self) -> None:
        """Clear all Captain's Log RAG data."""

        self._ensure_active()
        self._entries.clear()
