"""
rag.embedder

Light-weight, dependency-free embedder shim used by the RAG subsystem.

Right now this provides a **deterministic hash-based embedder** so that:

- The RAG pipeline has a working embedding interface.
- `PrimusCore.run_self_test()` can query status via `get_embedder_status()`.
- You can later swap in a “real” embedding model (e.g. sentence-transformers)
  without changing the rest of the codebase.

This module deliberately avoids external dependencies so the core system can
boot on a bare-bones environment.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence

logger = logging.getLogger(__name__)

# Public constants
EMBED_DIM: int = 384
DEFAULT_BACKEND: str = "hash-mock"


@dataclass(frozen=True)
class EmbedderConfig:
    """Configuration for the RAG embedder backend."""
    backend: str = DEFAULT_BACKEND
    dim: int = EMBED_DIM


class RAGEmbedder:
    """
    Simple, deterministic mock embedder used for bootstrapping and testing.

    This does NOT produce semantically meaningful vectors; it just turns text
    into a stable numeric vector so the rest of the RAG stack can be developed.
    """
    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self._config = config or EmbedderConfig()
        logger.info(
            "Initializing RAG embedder backend %r (dim=%d)",
            self._config.backend,
            self._config.dim,
        )

    @property
    def backend(self) -> str:
        return self._config.backend

    @property
    def dim(self) -> int:
        return self._config.dim

    # ---- Public embedding API -------------------------------------------------

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string into a fixed-size vector."""
        return _hash_embed(text, self._config.dim)

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of strings into vectors."""
        return [_hash_embed(t, self._config.dim) for t in texts]


# ---- Internal hashing-based mock backend --------------------------------------


def _hash_embed(text: str, dim: int) -> List[float]:
    """
    Deterministic hash-based embedding.

    - Uses SHA-256 over the UTF-8 text.
    - Expands/repeats digest bytes to the requested dimension.
    - Normalizes each byte into [-1.0, 1.0].
    """
    if dim <= 0:
        raise ValueError("dim must be positive")

    if not text:
        return [0.0] * dim

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    dlen = len(digest)
    vec: List[float] = []

    for i in range(dim):
        b = digest[i % dlen]
        # Map 0..255 -> -1.0..1.0
        vec.append((b / 255.0) * 2.0 - 1.0)

    return vec


# ---- Singleton accessors used by PrimusCore/RAG stack ------------------------


_embedder_singleton: RAGEmbedder | None = None


def get_embedder() -> RAGEmbedder:
    """
    Return a process-wide singleton RAGEmbedder.

    This is what other modules (indexer, retriever, PrimusCore) should call.
    """
    global _embedder_singleton
    if _embedder_singleton is None:
        _embedder_singleton = RAGEmbedder()
    return _embedder_singleton


def get_embedder_status() -> dict:
    """
    Status payload used by PrimusCore.run_self_test().

    Must at least return:
      - backend: str
      - dim: int
      - configured: bool
    """
    emb = get_embedder()
    return {
        "backend": emb.backend,
        "dim": emb.dim,
        "configured": True,
    }


__all__ = [
    "EMBED_DIM",
    "EmbedderConfig",
    "RAGEmbedder",
    "get_embedder",
    "get_embedder_status",
]