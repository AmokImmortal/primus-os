"""
RAG indexer with paragraph-aware chunking for PRIMUS OS.

This module keeps the public API stable while improving retrieval quality by
splitting documents into coherent chunks before embedding. Chunk metadata
includes the file path and a per-file chunk identifier so retrievers can return
precise passages instead of whole-file blobs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 750
DEFAULT_OVERLAP = 120
DEFAULT_MIN_CHUNK_SIZE = 60


class HashEmbedder:
    """Deterministic, dependency-free embedder used for local indexing."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(text) for text in texts]

    def _hash_to_vector(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
        values: List[float] = []
        while len(values) < self.dim:
            for i in range(0, len(digest), 4):
                if len(values) >= self.dim:
                    break
                chunk = digest[i : i + 4]
                val = int.from_bytes(chunk, byteorder="big", signed=False)
                values.append(val / float(2**32))
        return values


class RAGIndexer:
    """Index files into a JSON index with chunk-level metadata and vectors."""

    def __init__(self, index_dir: Path | None = None):
        self.index_dir = index_dir or Path(__file__).resolve().parent / "indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = HashEmbedder()

    # --------------------
    # Public API
    # --------------------
    def index_path(self, name: str, path: Path | str, recursive: bool = True) -> dict:
        base_path = Path(path)
        if not base_path.exists():
            raise FileNotFoundError(path)

        documents: List[dict] = []
        vectors: List[List[float]] = []

        for file_path in self._iter_files(base_path, recursive):
            text = self._read_text(file_path)
            if not text.strip():
                logger.info("Skipping empty file: %s", file_path)
                continue

            chunks = self._chunk_text(text)
            if not chunks:
                logger.info("No chunks produced for %s; skipping", file_path)
                continue

            logger.info("Indexing file %s -> %d chunks", file_path, len(chunks))
            chunk_vectors = self.embedder.embed_batch(chunks)
            for idx, chunk_text in enumerate(chunks):
                documents.append(
                    {
                        "text": chunk_text,
                        "path": str(file_path),
                        "chunk_id": idx,
                        "source": "file",
                    }
                )
            vectors.extend(chunk_vectors)

        index_path = self.index_dir / f"{name}.index.json"
        payload = {
            "name": name,
            "documents": documents,
            "vectors": vectors,
        }

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info("Index written: %s (%d documents)", index_path, len(documents))
        return {
            "status": "ok",
            "documents": len(documents),
            "index_path": str(index_path),
        }

    # --------------------
    # Internal helpers
    # --------------------
    def _iter_files(self, path: Path, recursive: bool) -> Iterable[Path]:
        if path.is_file():
            yield path
            return

        walker = path.rglob("*") if recursive else path.glob("*")
        for candidate in walker:
            if candidate.is_file():
                yield candidate

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", path, exc)
            return ""

    def _chunk_text(
        self,
        text: str,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap: int = DEFAULT_OVERLAP,
        min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
    ) -> List[str]:
        paragraphs = self._split_paragraphs(text)
        if not paragraphs:
            return []

        base_chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if para_len > max_chars:
                # Flush current chunk before handling oversized paragraph
                if current:
                    chunk = "\n\n".join(current)
                    if chunk.strip():
                        base_chunks.append(chunk)
                    current = []
                    current_len = 0
                base_chunks.extend(self._split_long_paragraph(para, max_chars, overlap))
                continue

            if current_len + (2 if current else 0) + para_len <= max_chars:
                current.append(para)
                current_len += para_len + (2 if current_len > 0 else 0)
            else:
                chunk = "\n\n".join(current)
                if chunk.strip():
                    base_chunks.append(chunk)
                current = [para]
                current_len = para_len

        if current:
            chunk = "\n\n".join(current)
            if chunk.strip():
                base_chunks.append(chunk)

        # Apply overlap between chunks
        chunks_with_overlap: List[str] = []
        for i, chunk in enumerate(base_chunks):
            if i > 0 and overlap > 0:
                prefix = base_chunks[i - 1][-overlap:]
                chunk = f"{prefix}\n{chunk}" if prefix else chunk
            if len(chunk) < min_chunk_size and len(base_chunks) > 1:
                continue
            chunks_with_overlap.append(chunk)

        return chunks_with_overlap

    def _split_paragraphs(self, text: str) -> List[str]:
        parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        if parts:
            return parts
        stripped = text.strip()
        return [stripped] if stripped else []

    def _split_long_paragraph(self, para: str, max_chars: int, overlap: int) -> List[str]:
        chunks: List[str] = []
        if not para:
            return chunks

        step = max(1, max_chars - overlap)
        start = 0
        while start < len(para):
            end = min(len(para), start + max_chars)
            chunk = para[start:end]
            chunks.append(chunk)
            if end >= len(para):
                break
            start += step
        return chunks


def index_path(name: str, path: Path | str, recursive: bool = True) -> dict:
    """Public helper that preserves the legacy API."""

    indexer = RAGIndexer()
    return indexer.index_path(name=name, path=path, recursive=recursive)


__all__ = ["RAGIndexer", "index_path"]
