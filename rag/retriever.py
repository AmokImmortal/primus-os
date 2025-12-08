from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rag.embedder import RAGEmbedder, get_embedder

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Simple RAG retriever that scores stored document vectors against a
    query embedding using cosine similarity.
    """

    def __init__(self, index_root: str | Path = "rag_index", embedder: Optional[RAGEmbedder] = None) -> None:
        self.index_root = Path(index_root)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.embedder: RAGEmbedder = embedder or get_embedder()

    # ------------------------------------------------------------------ #
    # Index loading helpers                                              #
    # ------------------------------------------------------------------ #

    def _index_path(self, name: str) -> Path:
        return self.index_root / f"{name}.json"

    def _load_index(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load an index file created by RAGIndexer.

        Expected structure:
        {
            "documents": [ { "path": str, "text": str }, ... ],
            "vectors":   [ [float, float, ...], ... ]
        }
        """
        path = self._index_path(name)
        if not path.exists():
            logger.warning("RAGRetriever: index '%s' not found at %s", name, path)
            return None

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "RAGRetriever: failed to load index '%s' from %s: %s",
                name,
                path,
                exc,
            )
            return None

        docs = data.get("documents") or []
        vecs = data.get("vectors") or []
        if len(docs) != len(vecs):
            logger.warning(
                "RAGRetriever: index '%s' has mismatched docs (%d) and vectors (%d)",
                name,
                len(docs),
                len(vecs),
            )

        return {"documents": docs, "vectors": vecs}

    # ------------------------------------------------------------------ #
    # Similarity                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0

        dot = 0.0
        mag1 = 0.0
        mag2 = 0.0

        for a, b in zip(v1, v2):
            dot += a * b
            mag1 += a * a
            mag2 += b * b

        if mag1 <= 0.0 or mag2 <= 0.0:
            return 0.0

        return dot / (math.sqrt(mag1) * math.sqrt(mag2))

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def retrieve(self, name: str, query: str, top_k: int = 3) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Retrieve the top_k most similar documents from the given index.

        Returns a list of (score, document_dict) tuples.
        """
        index = self._load_index(name)
        if not index:
            logger.info("RAGRetriever: index '%s' is empty or missing; no results.", name)
            return []

        documents: List[Dict[str, Any]] = index["documents"]
        vectors: List[List[float]] = index["vectors"]

        query_vec = self.embedder.embed_text(query)
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for doc, vec in zip(documents, vectors):
            score = self._cosine_similarity(query_vec, vec)
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        if top_k > 0:
            scored = scored[:top_k]

        return scored


__all__ = ["RAGRetriever"]
