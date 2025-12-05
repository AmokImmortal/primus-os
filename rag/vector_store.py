# vector_store.py
"""
PRIMUS RAG - Vector store with Master-Controlled access hooks

Location:
  C:\P.R.I.M.U.S OS\System\rag\vector_store.py

Features:
- FAISS backend (if installed) with numpy fallback
- Persistent metadata and index saving/loading
- Permission check hooks to support Master-controlled access (Option C)
  - Callers may pass `permission_check(requester, metadata) -> bool`
  - By default: any metadata with metadata.get("private", False)==True is denied
    to non-master requesters (i.e., default policy enforces "no private access")
- Methods:
    - info()
    - add(vectors, metadatas)
    - save()
    - load(permission_check=None)
    - search(qvec, topk=5, requester=None, permission_check=None)
    - clear()
"""

import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import numpy as np

# Try to import faiss (optional)
USE_FAISS = True
try:
    import faiss  # type: ignore
except Exception:
    USE_FAISS = False

# Filesystem paths
HERE = Path(__file__).resolve().parent  # .../System/rag
VECTOR_STORE_DIR = HERE / "vector_store"
METADATA_PATH = VECTOR_STORE_DIR / "metadata.json"
FAISS_INDEX_PATH = VECTOR_STORE_DIR / "index.faiss"
NP_ARRAY_PATH = VECTOR_STORE_DIR / "vectors.npy"

VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)


# Type alias for permission check function
PermissionFn = Callable[[Optional[str], Dict[str, Any]], bool]


def default_permission_check(requester: Optional[str], metadata: Dict[str, Any]) -> bool:
    """
    Default permission policy for Option C (Master-Controlled):
      - If metadata contains "private": true -> deny by default (return False)
      - Otherwise allow (return True)

    Master-level callers may override by providing their own permission function
    that recognizes the master user/role and returns True for private items.
    """
    if metadata.get("private", False):
        return False
    return True


class VectorStore:
    """
    VectorStore with permission hooks.

    Example usage (ingest path):
        store = VectorStore(backend="faiss")
        store.add(vectors, metadata_list)
        store.save()

    Example usage (query path):
        # permission_check provided by PRIMUS master/agent_manager
        store = VectorStore(backend="faiss")
        loaded = store.load(permission_check=my_perm_fn)
        results = store.search(query_vec, topk=5, requester="FileAgent", permission_check=my_perm_fn)
    """

    def __init__(self, backend: Optional[str] = None):
        # select backend
        if backend is None:
            self.backend = "faiss" if USE_FAISS else "fallback"
        else:
            if backend == "faiss" and not USE_FAISS:
                raise RuntimeError("FAISS requested but not available.")
            self.backend = backend

        # runtime state
        self.metadata: Dict[str, Dict[str, Any]] = {}  # id -> metadata
        self.ids: List[str] = []                       # insertion order (index -> id)
        self.vectors: Optional[np.ndarray] = None      # (N, dim) numpy array
        self.index = None                              # faiss index instance if used
        self.dim: Optional[int] = None

        # Attempt to load pre-existing store (metadata + index/vectors)
        self._load_metadata()
        self._load_index_if_exists()

    # -------------------------
    # Metadata persistence
    # -------------------------
    def _load_metadata(self):
        if METADATA_PATH.exists():
            try:
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, dict):
                    self.metadata = obj
                    self.ids = list(obj.keys())
                    return
            except Exception as e:
                print("[vector_store] Failed to parse metadata.json:", e)
        # default empty
        self.metadata = {}
        self.ids = []

    def _save_metadata(self):
        try:
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[vector_store] Failed to save metadata:", e)

    # -------------------------
    # Backend index management
    # -------------------------
    def _init_faiss_index(self, dim: int):
        if not USE_FAISS:
            raise RuntimeError("FAISS backend not available.")
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        if self.vectors is not None and len(self.vectors) > 0:
            self.index.add(self.vectors.astype("float32"))

    def _load_index_if_exists(self):
        # Try FAISS index first
        if self.backend == "faiss" and FAISS_INDEX_PATH.exists() and USE_FAISS:
            try:
                self.index = faiss.read_index(str(FAISS_INDEX_PATH))
                self.dim = self.index.d
                print("[vector_store] Loaded FAISS index from disk.")
                return
            except Exception as e:
                print("[vector_store] Could not read FAISS index:", e)

        # Fallback: numpy vectors
        if NP_ARRAY_PATH.exists():
            try:
                arr = np.load(str(NP_ARRAY_PATH))
                if arr is not None:
                    self.vectors = np.asarray(arr, dtype=np.float32)
                    if self.vectors.ndim == 2:
                        self.dim = self.vectors.shape[1]
                    print("[vector_store] Loaded numpy vectors from disk.")
            except Exception as e:
                print("[vector_store] Could not load numpy vectors:", e)

    def save(self) -> Dict[str, Any]:
        # persist metadata
        self._save_metadata()
        # persist backend index/vectors
        try:
            if self.backend == "faiss" and USE_FAISS and self.index is not None:
                faiss.write_index(self.index, str(FAISS_INDEX_PATH))
                print("[vector_store] FAISS index saved.")
            else:
                if self.vectors is not None:
                    np.save(str(NP_ARRAY_PATH), self.vectors)
                    print("[vector_store] Numpy vectors saved.")
        except Exception as e:
            print("[vector_store] Save error:", e)
            return {"status": "error", "error": str(e)}
        return {"status": "ok"}

    # -------------------------
    # Add vectors + metadata
    # -------------------------
    def add(self, vectors: np.ndarray, metadatas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add vectors and corresponding metadata.
        Each metadata entry may optionally contain "private": true to mark the chunk private.
        """
        if vectors is None or len(vectors) == 0:
            return {"status": "error", "error": "no_vectors"}

        vectors = np.asarray(vectors, dtype=np.float32)
        n, d = vectors.shape

        if self.dim is None:
            self.dim = d

        if d != self.dim:
            return {"status": "error", "error": f"dim_mismatch (expected {self.dim}, got {d})"}

        if len(metadatas) != n:
            return {"status": "error", "error": "metadata_vector_length_mismatch"}

        new_ids = []
        for md in metadatas:
            uid = str(uuid.uuid4())
            new_ids.append(uid)
            # store metadata (no id collision expected)
            self.metadata[uid] = md

        # append vectors
        if self.vectors is None:
            self.vectors = vectors
        else:
            self.vectors = np.vstack([self.vectors, vectors])

        # faiss add
        if self.backend == "faiss" and USE_FAISS:
            if self.index is None:
                self._init_faiss_index(self.dim)
            try:
                self.index.add(vectors)
            except Exception as e:
                print("[vector_store] FAISS add error:", e)
                # continue with numpy fallback (vectors are still kept in self.vectors)

        # update ids order
        self.ids.extend(new_ids)

        # persist metadata
        self._save_metadata()
        return {"status": "ok", "added": n, "ids": new_ids}

    # -------------------------
    # Load (with optional permission check)
    # -------------------------
    def load(self, permission_check: Optional[PermissionFn] = None) -> Dict[str, Any]:
        """
        Load index + metadata from disk. If permission_check is provided, it is not used
        to filter the index itself (index must be loaded completely), but callers can pass
        permission_check to `search()` to enforce per-request filtering.
        """
        # Load metadata (already attempted on init, but re-run)
        self._load_metadata()
        # Load index / numpy vectors if present
        self._load_index_if_exists()

        # We consider load successful if metadata exists (or empty) and backend index is null/loaded
        return {"status": "ok"}

    # -------------------------
    # Search (with permission filtering)
    # -------------------------
    def search(
        self,
        qvec: np.ndarray,
        topk: int = 5,
        requester: Optional[str] = None,
        permission_check: Optional[PermissionFn] = None
    ) -> List[Dict[str, Any]]:
        """
        Search and return results whose metadata passes permission_check(requester, metadata).
        - qvec: shape (dim,) or (1,dim)
        - requester: an identifier (e.g., "FileAgent" or "PRIMUS_Master") used by permission_check
        - permission_check: function(requester, metadata) -> bool
            If omitted, default_permission_check is used (private items denied).
        """
        if self.dim is None:
            return []

        if permission_check is None:
            permission_check = default_permission_check

        q = np.asarray(qvec, dtype=np.float32).reshape(1, -1)

        results = []
        try:
            if self.backend == "faiss" and USE_FAISS and self.index is not None:
                D, I = self.index.search(q, topk * 3)  # retrieve a larger candidate set, filter later
                # iterate candidates in returned order
                seen = 0
                for score, idx in zip(D[0], I[0]):
                    if idx == -1:
                        continue
                    if idx >= len(self.ids):
                        continue
                    _id = self.ids[idx]
                    md = self.metadata.get(_id, {})
                    # permission check
                    try:
                        allowed = bool(permission_check(requester, md))
                    except Exception as e:
                        print("[vector_store] permission_check error:", e)
                        allowed = False
                    if not allowed:
                        continue
                    results.append({
                        "id": _id,
                        "score": float(score),
                        "metadata": md
                    })
                    seen += 1
                    if seen >= topk:
                        break
                return results

            else:
                # fallback brute force (cosine similarity)
                if self.vectors is None or len(self.vectors) == 0:
                    return []
                vecs = self.vectors
                qnorm = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)
                vnorm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12)
                sims = (vnorm @ qnorm.T).reshape(-1)
                idxs = np.argsort(-sims)
                count = 0
                for idx in idxs:
                    if idx >= len(self.ids):
                        continue
                    _id = self.ids[idx]
                    md = self.metadata.get(_id, {})
                    try:
                        allowed = bool(permission_check(requester, md))
                    except Exception as e:
                        print("[vector_store] permission_check error:", e)
                        allowed = False
                    if not allowed:
                        continue
                    results.append({
                        "id": _id,
                        "score": float(sims[idx]),
                        "metadata": md
                    })
                    count += 1
                    if count >= topk:
                        break
                return results
        except Exception as e:
            print("[vector_store] Search error:", e)
            return []

    # -------------------------
    # Utilities
    # -------------------------
    def info(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "dim": self.dim,
            "count": len(self.ids),
            "metadata_file": str(METADATA_PATH),
            "index_file": str(FAISS_INDEX_PATH) if self.backend == "faiss" else str(NP_ARRAY_PATH),
            "faiss_available": USE_FAISS
        }

    def clear(self):
        """Clear vectors and metadata (use with caution)."""
        self.metadata = {}
        self.ids = []
        self.vectors = None
        self.index = None
        try:
            if METADATA_PATH.exists():
                METADATA_PATH.unlink()
            if FAISS_INDEX_PATH.exists():
                FAISS_INDEX_PATH.unlink()
            if NP_ARRAY_PATH.exists():
                NP_ARRAY_PATH.unlink()
        except Exception as e:
            print("[vector_store] clear error:", e)
        print("[vector_store] Cleared store.")