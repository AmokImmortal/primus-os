"""
RAG retriever for PRIMUS OS.

Loads chunked JSON indexes produced by rag.indexer, embeds queries with the
same deterministic hash embedder, scores documents, and returns the best
matching chunks.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rag.indexer import HashEmbedder

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieve relevant chunks from a named RAG index."""

    def __init__(self, index_dir: Optional[Path] = None):
        self.index_dir = index_dir or Path(__file__).resolve().parent / "indexes"
        self.embedder = HashEmbedder()

    def retrieve(self, name: str, query: str, top_k: int = 3) -> List[Tuple[float, Dict[str, Any]]]:
        """Return top_k (score, doc) pairs for the provided query and index name."""

        index_data = self._load_index(name)
        if not index_data:
            return []

        documents: List[Dict[str, Any]] = index_data.get("documents", []) or []
        vectors: List[List[float]] = index_data.get("vectors", []) or []
        candidate_count = min(len(documents), len(vectors))
        if candidate_count == 0:
            logger.info("RAGRetriever.retrieve: index='%s' has no documents", name)
            return []

        logger.info(
            "RAGRetriever.retrieve: index='%s' query_len=%d candidates=%d",
            name,
            len(query or ""),
            candidate_count,
        )

        query_vec = self.embedder.embed_batch([query or ""])[0]

        scored: List[Tuple[float, Dict[str, Any]]] = []
        seen = set()

        for doc, vec in zip(documents[:candidate_count], vectors[:candidate_count]):
            path = doc.get("path")
            chunk_id = doc.get("chunk_id")
            text = doc.get("text", "")
            key = (path, chunk_id if chunk_id is not None else text)
            if key in seen:
                continue
            seen.add(key)

            score = self._cosine_similarity(query_vec, vec)
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        limited = scored[: top_k if top_k is not None else len(scored)]
        logger.info(
            "RAGRetriever.retrieve: returning %d results (top_k=%s)",
            len(limited),
            top_k,
        )
        return limited

    # --------------------
    # Internal helpers
    # --------------------
    def _load_index(self, name: str) -> Optional[Dict[str, Any]]:
        path = self.index_dir / f"{name}.index.json"
        if not path.exists():
            logger.warning("RAGRetriever: index not found: %s", path)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("RAGRetriever: failed to load index %s", path)
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(dot / (norm_a * norm_b))


def get_retriever() -> RAGRetriever:
    return RAGRetriever()


__all__ = ["RAGRetriever", "get_retriever"]
