from __future__ import annotations

"""
Minimal offline RAG manager for PRIMUS OS.

Goals (Phase 1):
- Provide a concrete RAGManager so imports succeed and warnings disappear.
- Keep everything strictly local/offline (no HTTP, no external services).
- Support:
    - Adding documents with tags/metadata.
    - Simple text search (naive substring).
    - Status reporting for bootup tests.
- Respect permission scopes:
    - Use core.permissions.Scope for sensitivity.
    - Use core.security_gate.SecurityGate for outbound decisions later.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Iterable, Optional

from core.permissions import Scope, classify_scope_from_tags
from core.security_gate import get_security_gate


@dataclass
class RAGDocument:
    doc_id: str
    text: str
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: Scope = Scope.SYSTEM_PRIVATE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "scope": self.scope.name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGDocument":
        scope_name = data.get("scope", Scope.SYSTEM_PRIVATE.name)
        try:
            scope = Scope[scope_name]
        except KeyError:
            scope = Scope.SYSTEM_PRIVATE
        return cls(
            doc_id=str(data.get("doc_id", "")),
            text=str(data.get("text", "")),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            scope=scope,
        )


class RAGStore:
    """
    Very simple JSONL-backed store for RAG documents.

    This is intentionally minimal; later versions can replace this
    with embeddings, vector DBs, etc., without changing the manager API.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _iter_entries(self) -> Iterable[Dict[str, Any]]:
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def load_all(self) -> List[RAGDocument]:
        return [RAGDocument.from_dict(d) for d in self._iter_entries()]

    def append(self, doc: RAGDocument) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class RAGManager:
    """
    Offline RAG manager for PRIMUS.

    Responsibilities:
    - Manage a local corpus of RAGDocument objects.
    - Provide simple text search.
    - Respect Captain's Log / security model via scopes.
    """

    def __init__(self, store_path: Optional[Path] = None) -> None:
        if store_path is None:
            store_path = Path("rag/data/rag_corpus.jsonl")
        self.store = RAGStore(store_path)
        self._cache: List[RAGDocument] = []
        self._loaded: bool = False

    # -------------------------------------------------
    # Internal helpers
    # -------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._cache = self.store.load_all()
            self._loaded = True

    def _add_to_cache(self, doc: RAGDocument) -> None:
        self._cache.append(doc)

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------
    def index_document(
        self,
        doc_id: str,
        text: str,
        tags: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a new document to the RAG corpus.

        - scope is derived from tags using classify_scope_from_tags.
        - This is strictly offline; no external calls.
        """
        tags_list = list(tags or [])
        scope = classify_scope_from_tags(tags_list)
        doc = RAGDocument(
            doc_id=doc_id,
            text=text,
            tags=tags_list,
            metadata=metadata or {},
            scope=scope,
        )
        self._ensure_loaded()
        self._add_to_cache(doc)
        self.store.append(doc)

    def bulk_index(self, docs: Iterable[Dict[str, Any]]) -> None:
        """
        Bulk index convenience helper.

        Each dict is expected to have:
          - doc_id
          - text
          - tags (optional)
          - metadata (optional)
        """
        for d in docs:
            self.index_document(
                doc_id=str(d.get("doc_id", "")),
                text=str(d.get("text", "")),
                tags=d.get("tags"),
                metadata=d.get("metadata"),
            )

    def search(self, query: str, limit: int = 5) -> List[RAGDocument]:
        """
        Naive substring search over text.

        This does NOT talk to any external service. Results are fully local.
        """
        self._ensure_loaded()
        q = (query or "").strip().lower()
        if not q:
            return []

        results: List[RAGDocument] = []
        for doc in self._cache:
            if q in doc.text.lower():
                results.append(doc)
                if len(results) >= limit:
                    break
        return results

    def clear(self) -> None:
        """
        Clear the entire local RAG corpus.
        """
        self.store.clear()
        self._cache.clear()
        self._loaded = False

    # -------------------------------------------------
    # Status
    # -------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """
        Return a lightweight status dict for bootup tests.
        """
        self._ensure_loaded()
        return {
            "status": "ok",
            "documents": len(self._cache),
            "store_path": str(self.store.path),
        }

    # -------------------------------------------------
    # Outbound helper (placeholder for future use)
    # -------------------------------------------------
    def is_safe_for_external(self, doc: RAGDocument) -> bool:
        """
        Check whether this document is safe to send to an external service,
        given its scope and the current SecurityGate settings.
        """
        gate = get_security_gate()
        decision = gate.evaluate_outbound(scope=doc.scope)
        return decision.allowed






