# rag/retriever.py

import json
import math
from pathlib import Path
from rag.embedder import RAGEmbedder


class RAGRetriever:
    def __init__(self, index_root: str = "rag_index"):
        self.index_root = Path(index_root)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.embedder = RAGEmbedder()

    def _load_index(self, name: str):
        p = self.index_root / f"{name}.json"
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cosine(self, v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        mag1 = math.sqrt(sum(a * a for a in v1))
        mag2 = math.sqrt(sum(b * b for b in v2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    def retrieve(self, index_name: str, query: str, top_k: int = 3):
        data = self._load_index(index_name)
        if not data:
            return []

        qvec = self.embedder.embed_text(query)

        scored = []
        for doc, vec in zip(data["documents"], data["vectors"]):
            score = self._cosine(qvec, vec)
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]