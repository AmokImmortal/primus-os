import os
from pathlib import Path

from core.agent_manager import AgentManager
from core.model_manager import ModelManager
from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from rag.embedder import RAGEmbedder
from rag.indexer import RAGIndexer
from rag.retriever import RAGReteriever


class PrimusCore:
    def __init__(self, system_root: str):
        self.system_root = Path(system_root)

        self.agents_root = self.system_root / "agents"
        self.models_root = self.system_root / "models"
        self.memory_root = self.system_root / "memory"
        self.rag_index_root = self.system_root / "rag_index"

        self.agent_manager = AgentManager(self.agents_root)
        self.model_manager = ModelManager()
        self.memory_manager = MemoryManager(self.memory_root)
        self.session_manager = SessionManager()
        self.rag_embedder = RAGEmbedder()
        self.rag_indexer = RAGIndexer(self.rag_index_root)
        self.rag_retriever = RAGReteriever(self.rag_index_root)

        self.initialized = False

    def initialize(self):
        self.system_root.mkdir(parents=True, exist_ok=True)
        self.agents_root.mkdir(parents=True, exist_ok=True)
        self.models_root.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.rag_index_root.mkdir(parents=True, exist_ok=True)
        self.initialized = True
        return True

    def is_initialized(self):
        return self.initialized

    # -------------------------
    # RAG index + retrieval API
    # -------------------------

    def rag_index_path(self, name: str, path: str, recursive: bool = False):
        return self.rag_indexer.index_path(name, path, recursive=recursive)

    def rag_retrieve(self, name: str, query: str, top_k: int = 3):
        return self.rag_retriever.retrieve(name, query, top_k=top_k)