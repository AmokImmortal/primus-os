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
import math
from dataclasses import dataclass
from typing import Iterable, List, Dict, Any, Optional, Sequence

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Configuration & data structures
# -----------------------------------------------------------------------------

DEFAULT_EMBED_DIM = 384  # Safe, typical dimensionality for many text embedders


@dataclass
class EmbedderConfig:
    """Configuration for the local embedder backend."""

    dim: int = DEFAULT_EMBED_DIM
    backend_name: str = "hash-mock"  # descriptive label for self-test / logs


class SimpleHashEmbedder:
    """
    Deterministic, stateless hash-based embedder.

    This is a stand-in backend that maps text to a pseudo-random but
    deterministic vector, using SHA-256 under the hood. It is *not* a semantic
    embedding model, but it gives upstream code something vector-shaped to work
    with so the RAG pipeline can be developed and tested.

    You can later replace this with a real model (e.g. sentence-transformers)
    by:
      - Adding a new backend class.
      - Updating `_create_embedder_from_config()` to instantiate it.
    """

    def __init__(self, config: EmbedderConfig) -> None:
        self.config = config
        self.dim = config.dim
        self.backend_name = config.backend_name

    # ------------------------------------------------------------------ #
    # Core embedding methods
    # ------------------------------------------------------------------ #

    def embed(self, text: str, *, normalize: bool = True) -> List[float]:
        """Embed a single text string into a vector of length `self.dim`."""
        if not isinstance(text, str):
            raise TypeError(f"text must be str, got {type(text)!r}")

        # Normalize whitespace for determinism
        normalized = " ".join(text.split())
        digest = hashlib.sha256(normalized.encode("utf-8")).digest()

        # Expand digest to required length by repeated hashing
        raw_bytes = bytearray()
        counter = 0
        while len(raw_bytes) < self.dim * 4:
            counter_bytes = counter.to_bytes(4, "little", signed=False)
            raw_bytes.extend(hashlib.sha256(digest + counter_bytes).digest())
            counter += 1

        # Convert bytes to floats in [-1, 1]
        values: List[float] = []
        for i in range(self.dim):
            chunk = raw_bytes[i * 4 : (i + 1) * 4]
            int_val = int.from_bytes(chunk, "little", signed=False)
            # Map to [-1, 1]
            values.append((int_val / 2**31) - 1.0)

        if normalize:
            self._normalize_inplace(values)

        return values

    def embed_batch(
        self, texts: Sequence[str], *, normalize: bool = True
    ) -> List[List[float]]:
        """Embed a batch of texts."""
        return [self.embed(t, normalize=normalize) for t in texts]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_inplace(vec: List[float]) -> None:
        """Normalize a vector to unit L2 norm in-place, if non-zero."""
        norm_sq = sum(x * x for x in vec)
        if norm_sq <= 0.0:
            return
        inv_norm = 1.0 / math.sqrt(norm_sq)
        for i, x in enumerate(vec):
            vec[i] = x * inv_norm


# -----------------------------------------------------------------------------
# Global embedder instance (lazy-initialized)
# -----------------------------------------------------------------------------

_EMBEDDER: Optional[SimpleHashEmbedder] = None
_CONFIG = EmbedderConfig()  # You can later wire this from a central config


def _create_embedder_from_config(config: EmbedderConfig) -> SimpleHashEmbedder:
    """
    Factory for the current embedder backend.

    If you later introduce a real embedder, this is the only place that
    needs to be updated to pick a different backend based on configuration.
    """
    logger.info(
        "Initializing RAG embedder backend '%s' (dim=%d)",
        config.backend_name,
        config.dim,
    )
    return SimpleHashEmbedder(config)


def get_embedder() -> SimpleHashEmbedder:
    """
    Return the global embedder instance, creating it on first use.

    This keeps initialization lazy (no work done unless the RAG system
    actually calls into the embedder).
    """
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = _create_embedder_from_config(_CONFIG)
    return _EMBEDDER


# -----------------------------------------------------------------------------
# Public convenience API
# -----------------------------------------------------------------------------

def embed_text(text: str, *, normalize: bool = True) -> List[float]:
    """Embed a single text string using the default embedder."""
    return get_embedder().embed(text, normalize=normalize)


def embed_texts(
    texts: Iterable[str],
    *,
    normalize: bool = True,
) -> List[List[float]]:
    """
    Embed an iterable of texts using the default embedder.

    `texts` may be any iterable, but is internally materialized into a list to
    allow multiple passes if needed by future backends.
    """
    materialized = list(texts)
    if not materialized:
        return []
    return get_embedder().embed_batch(materialized, normalize=normalize)


def get_embedder_status() -> Dict[str, Any]:
    """
    Return a status dictionary describing the embedder backend.

    This is consumed by `PrimusCore.run_self_test()` like:

        status = get_embedder_status()
        results["rag"] = {"status": "ok", **status}

    So this function must **not** raise on normal paths; errors should be
    encoded into the returned dict instead, while logging for debugging.
    """
    try:
        emb = get_embedder()
        return {
            "backend": emb.backend_name,
            "dim": emb.dim,
            "configured": True,
        }
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("Embedder status check failed: %s", exc)
        return {
            "backend": "unavailable",
            "configured": False,
            "detail": str(exc),
        }