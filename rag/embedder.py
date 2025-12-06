# rag/embedder.py
#!/usr/bin/env python3
"""
Lightweight RAG embedding backend for PRIMUS OS.

This module is intentionally simple and offline-friendly:

- Provides a tiny RAGManager wrapper used by PrimusCore.
- Uses a trivial hash-based "embedding" so that:
    * The code runs without external dependencies.
    * The RAG self-test can verify the pipeline end-to-end.
- Can be replaced later with a real embedding backend (e.g. sentence-transformers,
  OpenAI embeddings, etc.) without changing the PrimusCore interface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


class RAGManager:
    """
    Minimal RAG manager that:
      - Stores a tiny local "index" as JSON in <system_root>/rag/index.jsonl
      - Exposes a very small self_test() API used by PrimusCore.run_self_test()
      - Provides basic add_documents() and search() hooks for future expansion.
    """

    def __init__(self, system_root: Path | str):
        self.system_root = Path(system_root)
        self.rag_dir = self.system_root / "rag"
        self.rag_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.rag_dir / "index.jsonl"

    # -----------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------

    def _hash_text(self, text: str) -> List[float]:
        """
        Extremely simple "embedding": SHA256 -> list of floats in [0, 1].

        This is NOT semantically meaningful; it's only here so that the
        pipeline has something to operate on without external libraries.
        """
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Take first 16 bytes and normalize to [0, 1]
        return [b / 255.0 for b in h[:16]]

    def _add_to_index(self, doc_id: str, text: str, meta: Dict[str, Any]) -> None:
        embedding = self._hash_text(text)
        record = {
            "id": doc_id,
            "text": text,
            "embedding": embedding,
            "meta": meta,
        }
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _iter_index(self) -> Iterable[Dict[str, Any]]:
        if not self.index_path.exists():
            return []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    def add_documents(
        self,
        docs: Iterable[Tuple[str, str]],
        meta: Dict[str, Any] | None = None,
    ) -> int:
        """
        Add (id, text) documents to the index.

        Returns the number of documents successfully added.
        """
        meta = meta or {}
        count = 0
        for doc_id, text in docs:
            self._add_to_index(doc_id, text, meta)
            count += 1
        return count

    def embed_text(self, text: str) -> List[float]:
        """Return a deterministic numeric embedding for a single text string."""
        return self._hash_text(text)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Extremely naive "similarity" search:
          - Embed the query.
          - Compute L1 distance from each stored embedding.
          - Return the closest top_k items.
        """
        q_emb = self._hash_text(query)
        results: List[Tuple[float, Dict[str, Any]]] = []

        for rec in self._iter_index():
            emb = rec.get("embedding")
            if not isinstance(emb, list):
                continue
            # L1 distance between embeddings
            dist = sum(abs((float(a) if a is not None else 0.0) - float(b)) for a, b in zip(q_emb, emb))
            results.append((dist, rec))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results[:top_k]]

    # -----------------------------------------------------
    # Self-test used by PrimusCore
    # -----------------------------------------------------

    def self_test(self) -> Dict[str, Any]:
        """
        Very small self-test used by PrimusCore.run_self_test().

        Verifies that:
          - The rag directory is writable.
          - We can add a document to the index.
          - We can perform a trivial search over that index.
        """
        result: Dict[str, Any] = {"status": "ok"}
        try:
            # Ensure directory exists and is writable
            self.rag_dir.mkdir(parents=True, exist_ok=True)

            # Add a test document
            test_id = "selftest-doc"
            test_text = "This is a small RAG self-test document for PRIMUS OS."
            self._add_to_index(test_id, test_text, {"source": "selftest"})

            # Perform a tiny search
            hits = self.search("RAG self-test", top_k=1)
            result["hits_found"] = len(hits)
            result["index_path"] = str(self.index_path)
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
        return result