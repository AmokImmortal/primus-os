# rag_manager.py
"""
RAG Manager for PRIMUS OS (core/rag_manager.py)

Responsibilities:
- Ingest documents (chunking, embeddings) into scope-based vector stores
  (scopes: "system", "primus", "agents/<AgentName>").
- Perform similarity search with permission checks.
- Manage per-scope indexes and metadata on disk.
- Basic logging and simple permission model (expandable).
- Designed to be self-contained: does NOT rely on other project's
  VectorStore implementation so it can reliably create per-scope stores.

Notes:
- Embedding engine: tries to use (in order)
    1) `get_embedder()` from rag.embedder (if present)
    2) `Embedder` class from rag.embedder
    3) sentence-transformers directly (offline, local model)
- FAISS is used when available; falls back to numpy brute-force search.
- Paths:
    SYSTEM_ROOT = <...>/System (inferred from this file location)
    RAG_ROOT = SYSTEM_ROOT / "rag" / "vector_store"
- This file is written to be robust to differing VectorStore implementations
  in your repo; it manages its own scoped stores.
"""

from __future__ import annotations

import os
import json
import math
import uuid
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

# Try to import FAISS
USE_FAISS = True
try:
    import faiss  # type: ignore
except Exception:
    FAISS_IMPORT_ERROR = True
    USE_FAISS = False

# Try to import embedder helpers (best effort)
EmbedderClass = None
get_embedder_fn = None
try:
    # prefer the repository embedder API if available
    from rag.embedder import Embedder as EmbedderClass  # type: ignore
    try:
        from rag.embedder import get_embedder as get_embedder_fn  # type: ignore
    except Exception:
        get_embedder_fn = None
except Exception:
    EmbedderClass = None
    get_embedder_fn = None

# fallback: sentence-transformers if available
SENTENCE_TRANSFORMERS_AVAILABLE = True
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None  # type: ignore

# Logging
logger = logging.getLogger("primus.rag_manager")
if not logger.handlers:
    # Basic console logger if none configured globally
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[RAG] %(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(ch)
logger.setLevel(logging.INFO)


# ---------- Path helpers ----------
SYSTEM_ROOT = Path(__file__).resolve().parents[1]  # .../System
RAG_ROOT = SYSTEM_ROOT / "rag" / "vector_store"
RAG_ROOT.mkdir(parents=True, exist_ok=True)


# ---------- Utility functions ----------
def _ensure_scope_dir(scope: str) -> Path:
    """
    Create and return directory for a given scope.
    scope examples: "system", "primus", "agents/FileAgent"
    """
    safe_scope = scope.replace("/", "_")
    p = RAG_ROOT / safe_scope
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_json(path: Path, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- ScopedVectorStore (self-contained) ----------
class ScopedVectorStore:
    """
    Minimal per-scope vector store. Uses FAISS if available, otherwise numpy.
    Files:
      <scope_dir>/metadata.json
      <scope_dir>/vectors.npy  (fallback)
      <scope_dir>/index.faiss  (faiss)
    Metadata format: {id: {metadata dict}}
    IDs are UUIDs assigned on add.
    """

    def __init__(self, scope_dir: Path, use_faiss: Optional[bool] = None):
        self.scope_dir = Path(scope_dir)
        self.scope_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.scope_dir / "metadata.json"
        self.npy_path = self.scope_dir / "vectors.npy"
        self.index_path = self.scope_dir / "index.faiss"
        # choose backend
        if use_faiss is None:
            self.use_faiss = USE_FAISS
        else:
            self.use_faiss = bool(use_faiss) and USE_FAISS

        # in-memory structures
        self.ids: List[str] = []
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.vectors: Optional[np.ndarray] = None  # (N, dim) float32
        self.index = None  # faiss IndexFlatL2

        # try load existing
        self._load()

    def _load(self):
        # load metadata first
        if self.meta_path.exists():
            try:
                obj = _load_json(self.meta_path)
                if isinstance(obj, dict):
                    self.metadata = obj
                    self.ids = list(obj.keys())
                else:
                    self.metadata = {}
                    self.ids = []
            except Exception as e:
                logger.warning("Failed to load metadata: %s", e)
                self.metadata = {}
                self.ids = []
        else:
            self.metadata = {}
            self.ids = []

        # Load vectors/index
        if self.use_faiss and self.index_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                # dimension from index
                self.dim = self.index.d
                # We cannot extract raw vectors easily from FAISS index; keep vectors None
                logger.info("Loaded FAISS index for scope %s", self.scope_dir.name)
                return
            except Exception as e:
                logger.warning("Failed to read FAISS index: %s", e)
                self.index = None

        # fallback: load numpy array
        if self.npy_path.exists():
            try:
                arr = np.load(str(self.npy_path))
                self.vectors = np.asarray(arr, dtype=np.float32)
                if self.vectors.ndim == 2:
                    self.dim = self.vectors.shape[1]
                logger.info("Loaded numpy vectors for scope %s: %d vectors", self.scope_dir.name, 0 if self.vectors is None else len(self.vectors))
            except Exception as e:
                logger.warning("Failed to load numpy vectors: %s", e)
                self.vectors = None

    def info(self) -> Dict[str, Any]:
        return {
            "scope": self.scope_dir.name,
            "count": len(self.ids),
            "dim": None if self.vectors is None else (self.vectors.shape[1] if self.vectors.ndim == 2 else None),
            "use_faiss": self.use_faiss,
            "meta_path": str(self.meta_path),
            "index_path": str(self.index_path),
            "npy_path": str(self.npy_path),
        }

    def save(self):
        # save metadata
        _save_json(self.meta_path, self.metadata)
        # save vectors/index
        try:
            if self.use_faiss and self.index is not None:
                faiss.write_index(self.index, str(self.index_path))
                logger.info("Saved FAISS index for %s", self.scope_dir.name)
            else:
                if self.vectors is not None:
                    np.save(str(self.npy_path), self.vectors)
                    logger.info("Saved numpy vectors for %s", self.scope_dir.name)
        except Exception as e:
            logger.error("Error saving index/vectors: %s", e)

    def clear(self):
        self.ids = []
        self.metadata = {}
        self.vectors = None
        self.index = None
        # remove files
        try:
            if self.meta_path.exists():
                self.meta_path.unlink()
            if self.npy_path.exists():
                self.npy_path.unlink()
            if self.index_path.exists():
                self.index_path.unlink()
            logger.info("Cleared scoped store: %s", self.scope_dir)
        except Exception as e:
            logger.warning("Clear error: %s", e)

    def _init_index(self, dim: int):
        if self.use_faiss:
            self.index = faiss.IndexFlatL2(dim)
            # add existing vectors if present
            if self.vectors is not None and len(self.vectors) > 0:
                self.index.add(self.vectors.astype("float32"))
        else:
            # ensure numpy vectors exist
            if self.vectors is None:
                self.vectors = np.zeros((0, dim), dtype=np.float32)

    def add(self, vectors: np.ndarray, metadata_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add vectors (N, dim) and their metadata. Returns dict with ids added.
        """
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        n, d = vectors.shape
        # init dimension if necessary
        if (self.vectors is None) and (self.index is None):
            self._init_index(d)

        # dimension checks
        existing_dim = None
        if self.vectors is not None and self.vectors.size != 0:
            existing_dim = self.vectors.shape[1]
        if self.index is not None:
            try:
                existing_dim = self.index.d
            except Exception:
                pass
        if existing_dim is not None and existing_dim != d:
            return {"status": "error", "error": f"dim_mismatch expected {existing_dim} got {d}"}

        # assign ids and metadata
        new_ids = []
        for md in metadata_list:
            uid = str(uuid.uuid4())
            new_ids.append(uid)
            self.metadata[uid] = md

        # append vectors
        if self.use_faiss:
            if self.index is None:
                self._init_index(d)
            try:
                self.index.add(vectors)
            except Exception as e:
                logger.warning("FAISS add error: %s", e)
                # fallback to numpy append
                if self.vectors is None:
                    self.vectors = vectors
                else:
                    self.vectors = np.vstack([self.vectors, vectors])
        else:
            if self.vectors is None or self.vectors.size == 0:
                self.vectors = vectors
            else:
                self.vectors = np.vstack([self.vectors, vectors])

        self.ids.extend(new_ids)
        self.save()
        return {"status": "ok", "added": n, "ids": new_ids}

    def _search_faiss(self, q: np.ndarray, topk: int) -> List[Dict[str, Any]]:
        D, I = self.index.search(q.astype("float32"), topk)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx == -1:
                continue
            if idx < len(self.ids):
                _id = self.ids[idx]
                results.append({"id": _id, "score": float(score), "metadata": self.metadata.get(_id, {})})
        return results

    def _search_fallback(self, q: np.ndarray, topk: int) -> List[Dict[str, Any]]:
        if self.vectors is None or len(self.vectors) == 0:
            return []
        # cosine similarity
        qnorm = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)
        vnorm = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-12)
        sims = (vnorm @ qnorm.T).reshape(-1)
        idxs = np.argsort(-sims)[:topk]
        results = []
        for idx in idxs:
            if idx < len(self.ids):
                _id = self.ids[idx]
                results.append({"id": _id, "score": float(sims[idx]), "metadata": self.metadata.get(_id, {})})
        return results

    def search(self, qvec: np.ndarray, topk: int = 5) -> List[Dict[str, Any]]:
        q = np.asarray(qvec, dtype=np.float32).reshape(1, -1)
        try:
            if self.use_faiss and self.index is not None:
                return self._search_faiss(q, topk)
            else:
                return self._search_fallback(q, topk)
        except Exception as e:
            logger.error("Search error: %s", e)
            return []


# ---------- Permissions ----------
DEFAULT_PERMISSIONS = {
    # agent_name -> dict of capabilities
    # "FileAgent": {"read_system_rag": True, "write_own": True, "read_own": True, "access_private": False}
}


class PermissionManager:
    """
    Lightweight permission manager. Expandable as needed.
    """

    def __init__(self):
        # base defaults
        self.permissions: Dict[str, Dict[str, bool]] = {}
        self.global_defaults = {
            "read_system_rag": True,   # can read the shared system RAG
            "write_own": True,         # can write to their own agent RAG
            "read_own": True,          # can read their own RAG
            "access_private": False,   # access to private subchats / private RAG (denied by default)
            "agent_to_agent": False,   # allow direct agent->agent messaging/search
        }

    def register_agent(self, agent_name: str, overrides: Optional[Dict[str, bool]] = None):
        perms = dict(self.global_defaults)
        if overrides:
            perms.update(overrides)
        self.permissions[agent_name] = perms

    def can(self, agent_name: Optional[str], action: str) -> bool:
        """
        action examples: "read_system_rag", "write_own", "access_private", "agent_to_agent"
        agent_name: None represents Primus (superuser)
        """
        if agent_name is None:
            # Primus (superuser) allowed everything by default
            return True
        p = self.permissions.get(agent_name, dict(self.global_defaults))
        return bool(p.get(action, False))


# ---------- RAG Manager ----------
class RAGManager:
    """
    High-level manager for ingestion and search across scopes.
    """

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.perms = permission_manager or PermissionManager()
        # default register Primus as None (superuser)
        # create top-level scopes
        for s in ("system", "primus"):
            _ensure_scope_dir(s)

    def _get_scope_dir(self, scope: str) -> Path:
        return _ensure_scope_dir(scope)

    def ingest(self, path: str, scope: str = "system", agent_name: Optional[str] = None,
               chunk_size: int = 500, overlap: int = 50, model_name: str = "all-MiniLM-L6-v2") -> Dict[str, Any]:
        """
        Ingest text files from `path` into `scope`.
        If scope == "agents/<AgentName>" ensure agent_name matches and permission granted.
        """
        # permission checks
        if scope.startswith("agents/"):
            # ensure agent writing own store
            target_agent = scope.split("/", 1)[1]
            if agent_name is None or agent_name != target_agent:
                return {"status": "error", "error": "agent_name_mismatch"}
            if not self.perms.can(agent_name, "write_own"):
                return {"status": "error", "error": "permission_denied"}
        # read files
        p = Path(path)
        if not p.exists():
            return {"status": "error", "error": "path_not_found"}

        files = []
        for root, _, filenames in os.walk(p):
            for fn in filenames:
                if fn.lower().endswith((".txt", ".md")):
                    fp = Path(root) / fn
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            txt = f.read()
                        files.append((str(fp), txt))
                    except Exception as e:
                        logger.warning("Failed to read file %s: %s", fp, e)

        if not files:
            return {"status": "error", "error": "no_text_files_found"}

        def _chunk_text(text: str, size: int, overlap_size: int) -> List[Tuple[int, int, str]]:
            """
            Split text into overlapping chunks returning (start, end, chunk_text) tuples.

            Ensures forward progress even if size <= overlap_size.
            """

            if size <= 0:
                return []

            step = max(size - overlap_size, 1)
            chunks_local: List[Tuple[int, int, str]] = []
            start = 0
            text_length = len(text)

            while start < text_length:
                end = min(start + size, text_length)
                chunk_text = text[start:end]
                chunks_local.append((start, end, chunk_text))

                if end >= text_length:
                    break
                start += step

            return chunks_local

        # chunking
        all_vectors: List[np.ndarray] = []
        all_metadatas: List[Dict[str, Any]] = []

        embedder = self._get_embedder(model_name)
        if embedder is None:
            logger.warning("No embedder available; cannot embed chunks.")
            return {"status": "error", "error": "no_embedder"}

        for file_path, text in files:
            file_chunks = _chunk_text(text, chunk_size, overlap)
            if not file_chunks:
                continue

            chunk_texts = [chunk_text for _, _, chunk_text in file_chunks]
            vectors = embedder.embed(chunk_texts)
            vectors = np.asarray(vectors, dtype=np.float32)

            for idx, (start, end, chunk_text) in enumerate(file_chunks):
                all_metadatas.append({
                    "path": file_path,
                    "source_file": file_path,
                    "chunk_id": idx,
                    "chunk_index": len(all_metadatas),
                    "start": start,
                    "end": end,
                    "text": chunk_text,
                })

            all_vectors.append(vectors)

        total_chunks = len(all_metadatas)
        logger.info("Ingest: %d chunks prepared from %d files", total_chunks, len(files))

        if not all_vectors:
            return {"status": "error", "error": "no_chunks_embedded"}

        vectors_stacked = np.vstack(all_vectors) if len(all_vectors) > 1 else all_vectors[0]

        # create scoped store and add
        scope_dir = self._get_scope_dir(scope)
        store = ScopedVectorStore(scope_dir)
        add_res = store.add(vectors_stacked, all_metadatas)
        logger.info("Ingest add result: %s", add_res)
        return {"status": "ok", "added": add_res.get("added", 0), "chunks": total_chunks}

    def search(self, query: str, agent_name: Optional[str] = None, scope: str = "system",
               topk: int = 5, model_name: str = "all-MiniLM-L6-v2") -> List[Dict[str, Any]]:
        """
        Search within a scope. Permission rules apply:
         - Primus (agent_name=None) may search anywhere.
         - Agents may search system if allowed, their own scope, and other agent scopes only if agent_to_agent allowed.
        """
        # permission checks
        if agent_name is not None:
            # agent searching system
            if scope == "system" and not self.perms.can(agent_name, "read_system_rag"):
                return []
            # agent searching private/primus
            if scope == "primus" and not self.perms.can(agent_name, "access_private"):
                return []
            # agent searching other agents
            if scope.startswith("agents/"):
                target_agent = scope.split("/", 1)[1]
                if target_agent != agent_name and not self.perms.can(agent_name, "agent_to_agent"):
                    return []

        # load embedder
        embedder = self._get_embedder(model_name)
        if embedder is None:
            logger.warning("No embedder available for search.")
            return []

        qvec = embedder.embed([query])[0]

        scope_dir = self._get_scope_dir(scope)
        store = ScopedVectorStore(scope_dir)
        results = store.search(qvec, topk=topk)
        # attach human-friendly info
        for r in results:
            # if metadata exists, keep minimal preview
            md = r.get("metadata", {})
            if "text" in md:
                r["preview"] = (md["text"][:512] + ("..." if len(md["text"]) > 512 else ""))
            else:
                r["preview"] = ""
        return results

    def list_scopes(self) -> List[Dict[str, Any]]:
        out = []
        for d in RAG_ROOT.iterdir():
            if d.is_dir():
                store = ScopedVectorStore(d)
                out.append(store.info())
        return out

    def clear_scope(self, scope: str, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear a scope. Permission: only Primus (agent_name=None) or agent clearing own scope.
        """
        if scope.startswith("agents/"):
            target = scope.split("/", 1)[1]
            if agent_name is None:
                # primus allowed
                pass
            elif agent_name != target:
                return {"status": "error", "error": "permission_denied"}
        # perform clear
        scope_dir = self._get_scope_dir(scope)
        store = ScopedVectorStore(scope_dir)
        store.clear()
        return {"status": "ok"}

    # ---------- embedder helper ----------
    def _get_embedder(self, model_name: str):
        """
        Returns an object with method embed(list[str]) -> np.ndarray (N, dim).
        Priority:
          - repo get_embedder()
          - repo Embedder()
          - SentenceTransformer(model_name)
        """
        # repo get_embedder factory
        if get_embedder_fn is not None:
            try:
                return get_embedder_fn(model_name)
            except Exception as e:
                logger.warning("repo get_embedder failed: %s", e)

        # repo Embedder class
        if EmbedderClass is not None:
            try:
                inst = EmbedderClass(model_name=model_name)
                return inst
            except Exception as e:
                logger.warning("repo Embedder init failed: %s", e)

        # fallback to SentenceTransformer wrapper
        if SENTENCE_TRANSFORMERS_AVAILABLE and SentenceTransformer is not None:
            class _STWrapper:
                def __init__(self, model_name_local):
                    self.model = SentenceTransformer(model_name_local)
                    # SentenceTransformer returns numpy arrays directly
                def embed(self, texts: List[str]) -> np.ndarray:
                    if not texts:
                        return np.zeros((0, self.model.get_sentence_embedding_dimension()), dtype=np.float32)
                    return np.asarray(self.model.encode(texts, show_progress_bar=False), dtype=np.float32)
            try:
                return _STWrapper(model_name)
            except Exception as e:
                logger.warning("SentenceTransformer init failed: %s", e)

        logger.error("No embedding backend available.")
        return None


# -----------------------
# Example simple CLI utility (optional)
# -----------------------
def _cli():
    import argparse
    p = argparse.ArgumentParser(prog="rag_manager.py")
    p.add_argument("--ingest", help="Folder path to ingest into scope", nargs=2, metavar=("SCOPE", "PATH"))
    p.add_argument("--search", help="Search query", nargs=2, metavar=("SCOPE", "QUERY"))
    p.add_argument("--list", action="store_true", help="List RAG scopes")
    p.add_argument("--clear", help="Clear scope", metavar="SCOPE")
    args = p.parse_args()

    mgr = RAGManager()

    if args.ingest:
        scope, path = args.ingest
        res = mgr.ingest(path, scope)
        print("Ingest result:", res)
    elif args.search:
        scope, query = args.search
        res = mgr.search(query, scope=scope)
        print("Search results:", json.dumps(res, indent=2))
    elif args.list:
        for info in mgr.list_scopes():
            print(info)
    elif args.clear:
        print(mgr.clear_scope(args.clear))
    else:
        p.print_help()


if __name__ == "__main__":
    _cli()