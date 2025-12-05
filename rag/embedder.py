# embedder.py
"""
PRIMUS RAG embedder
- Provides Embedder class and get_embedder(model_name) helper.
- Uses sentence-transformers and PyTorch; auto-detects CUDA if available.
- Returns numpy float32 vectors suitable for FAISS.
Location: C:\P.R.I.M.U.S OS\System\rag\embedder.py
"""

import os
import math
from typing import List, Optional

import numpy as np

# Lazy import SentenceTransformer to allow graceful failure if not installed
try:
    from sentence_transformers import SentenceTransformer
except Exception as e:
    SentenceTransformer = None  # ingest/query will still handle this case


def _detect_device() -> str:
    """
    Decide whether to use 'cuda' or 'cpu'.
    You can override by setting environment variable PRIMUS_EMBED_DEVICE.
    """
    env = os.environ.get("PRIMUS_EMBED_DEVICE", "").lower()
    if env in ("cpu", "cuda"):
        return env
    # auto-detect
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class Embedder:
    """
    Wraps a SentenceTransformer model with batching & device handling.
    embed(texts: List[str]) -> np.ndarray shape (N, dim) dtype float32
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: Optional[str] = None, batch_size: int = 128):
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is not installed. Install with: pip install sentence-transformers")

        self.model_name = model_name
        self.device = device or _detect_device()
        self.batch_size = max(1, int(batch_size))

        # Load model
        # SentenceTransformer moves model to device in __init__ when calling .to()
        print(f"[Embedder] Loading model: {self.model_name}")
        try:
            # instantiate model
            self.model = SentenceTransformer(self.model_name)
            # attempt to move to desired device
            try:
                # This .to() call can be needed depending on sentence-transformers version
                self.model.to(self.device)
            except Exception:
                # Some versions already moved; ignore if fails
                pass
        except Exception as e:
            raise RuntimeError(f"[Embedder] Failed to load model '{self.model_name}': {e}")

        # determine embedding dimension by encoding an empty string
        try:
            dummy = self.model.encode([""], convert_to_numpy=True)
            self.dim = int(dummy.shape[1])
        except Exception:
            # fallback
            self.dim = None

        print(f"[Embedder] Device: {self.device}; Batch size: {self.batch_size}; Dim: {self.dim}")

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed a list of texts — returns numpy array shape (N, dim) dtype float32
        Batches automatically to avoid OOM.
        """
        if not isinstance(texts, list):
            raise ValueError("texts must be a list of strings")

        n = len(texts)
        if n == 0:
            return np.zeros((0, self.dim if self.dim else 0), dtype=np.float32)

        # guard: convert non-str to str
        texts = [t if isinstance(t, str) else str(t) for t in texts]

        # compute batch count
        batch_size = self.batch_size
        batches = math.ceil(n / batch_size)
        out = []

        for i in range(batches):
            start = i * batch_size
            end = min((i + 1) * batch_size, n)
            batch_texts = texts[start:end]
            try:
                emb = self.model.encode(batch_texts, convert_to_numpy=True, show_progress_bar=False)
            except TypeError:
                # older/newer API differences: try without convert_to_numpy
                emb = self.model.encode(batch_texts, show_progress_bar=False)
                # if returned list, convert
                if not isinstance(emb, np.ndarray):
                    emb = np.asarray(emb)

            # Ensure dtype float32
            emb = np.asarray(emb, dtype=np.float32)
            out.append(emb)

        result = np.vstack(out).astype(np.float32)

        # If we couldn't infer dim earlier, set it now
        if self.dim is None and result.ndim == 2:
            self.dim = result.shape[1]

        return result

    @property
    def using_gpu(self) -> bool:
        return self.device.startswith("cuda")


# Helper factory used by ingest.py and query.py
def get_embedder(model_name: str = "all-MiniLM-L6-v2", device: Optional[str] = None, batch_size: int = 128) -> Embedder:
    """
    Returns an Embedder instance. Kept as a helper for the scripts.
    """
    return Embedder(model_name=model_name, device=device, batch_size=batch_size)


# Simple CLI test (optional)
if __name__ == "__main__":
    # quick smoke test when executed directly
    model = os.environ.get("PRIMUS_TEST_MODEL", "all-MiniLM-L6-v2")
    e = get_embedder(model)
    print("[Embedder] Ready. Device:", e.device, "Dim:", e.dim)
    sample = ["Hello world", "This is a test"]
    vecs = e.embed(sample)
    print("[Embedder] Embedded", vecs.shape)