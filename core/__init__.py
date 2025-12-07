"""
Core package convenience exports for PRIMUS OS.

This module exposes lightweight helpers used by the CLI for RAG indexing and
retrieval without requiring callers to construct PrimusRuntime directly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.primus_core import PrimusCore, get_primus_core

logger = logging.getLogger(__name__)

# Track whether the shared PrimusCore has been initialized for RAG usage.
_core_initialized = False


def _ensure_core_initialized() -> PrimusCore:
    global _core_initialized
    core = get_primus_core(singleton=True)
    if not _core_initialized:
        try:
            core.initialize()
            _core_initialized = True
            logger.info("core.__init__: PrimusCore initialized for RAG helpers")
        except Exception:
            logger.exception("Failed to initialize PrimusCore for RAG helpers")
            raise
    return core


def rag_index_path(path: str, recursive: bool = False) -> Dict[str, Any]:
    """
    Index the given path into the system RAG scope.

    The recursive flag is accepted for CLI compatibility; directory traversal is
    delegated to the underlying RAG manager implementation.
    """

    core = _ensure_core_initialized()
    if not Path(path).exists():
        raise FileNotFoundError(path)

    if core.rag and hasattr(core.rag, "ingest_folder"):
        logger.info("core.rag_index_path: indexing path=%s recursive=%s", path, recursive)
        try:
            return core.rag.ingest_folder(path=path, scope="system", recursive=recursive)  # type: ignore[arg-type]
        except TypeError:
            # Older implementations may not accept the recursive flag.
            return core.rag.ingest_folder(path=path, scope="system")  # type: ignore[arg-type]

    # Fallback to PrimusCore.ingest API
    logger.info("core.rag_index_path: delegating to PrimusCore.ingest")
    return core.ingest(path=path, scope="system")


def rag_retrieve(index: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve relevant documents from the specified RAG index.
    """

    core = _ensure_core_initialized()
    if core.rag and hasattr(core.rag, "search"):
        logger.info(
            "core.rag_retrieve: searching index=%s query_length=%s top_k=%s",
            index,
            len(query),
            top_k,
        )
        return core.rag.search(query=query, scope=index, topk=top_k)  # type: ignore[arg-type]

    logger.info("core.rag_retrieve: delegating to PrimusCore.search_rag")
    res = core.search_rag(query=query, scope=index, topk=top_k)
    hits = res.get("hits") if isinstance(res, dict) else None
    return hits if isinstance(hits, list) else []


__all__ = ["rag_index_path", "rag_retrieve", "get_primus_core", "PrimusCore"]
