import os
import json
from pathlib import Path
from rag.embedder import RAGEmbedder


class RAGIndexer:
    def __init__(self, index_root: str = "rag_index"):
        self.index_root = Path(index_root)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.embedder = RAGEmbedder()

    def _load_index(self, name: str):
        p = self.index_root / f"{name}.json"
        if not p.exists():
            return {"documents": [], "vectors": []}
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_index(self, name: str, data):
        p = self.index_root / f"{name}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _gather_files(self, path: Path, recursive: bool):
        if path.is_file():
            return [path]
        if not recursive:
            return [p for p in path.iterdir() if p.is_file()]
        return [p for p in path.rglob("*") if p.is_file()]

    def index_path(self, path: str, recursive: bool = False):
        root = Path(path)
        files = self._gather_files(root, recursive=recursive)

        index_name = root.name
        index_data = self._load_index(index_name)

        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            vec = self.embedder.embed(text)

            index_data["documents"].append({"path": str(f), "text": text})
            index_data["vectors"].append(vec)

        self._save_index(index_name, index_data)