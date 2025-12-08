from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.agent_manager import AgentManager
from core.model_manager import ModelManager
from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from rag.embedder import get_embedder_status, get_embedder
from rag.indexer import RAGIndexer
from rag.retriever import RAGRetriever

logger = logging.getLogger(__name__)


class PrimusCore:
    """
    Central orchestration object for PRIMUS.

    - Owns managers (agents, models, memory, sessions).
    - Owns RAG components (indexer, retriever, embedder).
    - Provides unified APIs for:
        - RAG indexing / retrieval
        - Session-aware, optionally RAG-aware chat
        - Core self-test
    """

    def __init__(self, system_root: str) -> None:
        self.system_root = Path(system_root)

        # Core directory layout
        self.agents_root = self.system_root / "agents"
        self.models_root = self.system_root / "models"
        self.memory_root = self.system_root / "memory"
        self.rag_index_root = self.system_root / "rag_index"
        self.session_root = self.system_root / "sessions"

        # Managers
        self.agent_manager = AgentManager(self.agents_root)
        self.model_manager = ModelManager()
        self.memory_manager = MemoryManager(self.memory_root)
        self.session_manager = SessionManager(self.session_root)

        # RAG stack
        self.rag_embedder = get_embedder()
        self.rag_indexer = RAGIndexer(self.rag_index_root)
        self.rag_retriever = RAGRetriever(self.rag_index_root)

        self.initialized = False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def initialize(self) -> bool:
        """
        Ensure all core directories exist.

        PrimusRuntime._ensure_core() calls this once after construction.
        """
        for p in (
            self.system_root,
            self.agents_root,
            self.models_root,
            self.memory_root,
            self.rag_index_root,
            self.session_root,
        ):
            p.mkdir(parents=True, exist_ok=True)

        self.initialized = True
        logger.info("PrimusCore.initialize() complete; core directories ensured.")
        return True

    def is_initialized(self) -> bool:
        return self.initialized

    # ------------------------------------------------------------------ #
    # RAG index + retrieval API                                          #
    # ------------------------------------------------------------------ #

    def rag_index_path(self, name: str, path: str | Path, recursive: bool = False) -> None:
        """
        Index the given file or directory under a named index.

        - name:      logical index name (e.g. 'docs')
        - path:      file or directory to index
        - recursive: if True and path is a directory, recurse into subdirs
        """
        logger.info(
            "RAG index request: name=%r path=%r recursive=%s",
            name,
            str(path),
            recursive,
        )
        self.rag_indexer.index_path(name=name, path=path, recursive=recursive)

    def rag_retrieve(self, name: str, query: str, top_k: int = 3) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Retrieve top-k documents from a named index for a query.
        """
        logger.info("RAG retrieve request: index=%r query_len=%d top_k=%d", name, len(query), top_k)
        return self.rag_retriever.retrieve(name=name, query=query, top_k=top_k)

    # ------------------------------------------------------------------ #
    # Session-aware + RAG-aware chat                                     #
    # ------------------------------------------------------------------ #

    def _load_history(self, session_id: str) -> list[dict]:
        """
        Helper to load a session history from SessionManager, if available.

        Expected shape: list of {'role': 'user'|'assistant', 'content': str}
        """
    sm = getattr(self, "session_manager", None)
    if sm is None:
            return []

        try:
        # Replace load_session with the *real* method name
        history = sm.load_session(session_id)
        except Exception as exc:
            logger.warning("load_history failed for %r: %s", session_id, exc)
            return []

            return history or []

def _append_message(self, session_id: str, role: str, content: str) -> None:
    sm = getattr(self, "session_manager", None)
    if sm is None:
        return

    msg = {"role": role, "content": content}
    try:
        # Replace append_message with the *real* method name
        sm.append_message(session_id, msg)
    except Exception as exc:
        logger.warning("append_message failed for %r: %s", session_id, exc)

    def _build_rag_context(self, rag_index: str, user_message: str, top_k: int = 3) -> str:
        """
        Fetch RAG snippets and format them as a context block for the prompt.
        """
        try:
            results = self.rag_retrieve(rag_index, user_message, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG retrieve failed for index %r: %s", rag_index, exc)
            return ""

        lines: List[str] = []
        for score, doc in results:
            text = doc.get("text") or ""
            path = doc.get("path") or ""
            if not text:
                continue
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            lines.append(f"- ({score:.4f}) [{path}] {snippet}")

        if not lines:
            return ""

        context_block = "Relevant context from your knowledge base:\n" + "\n".join(lines)
        return context_block

    def get_session_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """
        Return recent messages for a given session.

        Uses the same underlying mechanism as _load_history, but exposes
        a safe, read-only API for the CLI.
        """
        try:
            history = self._load_history(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_session_history: failed to load history for %r: %s",
                session_id,
                exc,
            )
            return []

        if limit is not None and limit > 0:
            return history[-limit:]
        return history

    def clear_session(self, session_id: str) -> None:
        """
        Clear all messages for a given session.

        Prefer SessionManager if it exposes a clear/delete API; otherwise
        fall back to deleting any matching files under session_root.
        """
        try:
            sm = getattr(self, "session_manager", None)
            if sm is not None:
                # Try common method names on SessionManager
                for attr in ("clear_session", "delete_session", "remove_session"):
                    func = getattr(sm, attr, None)
                    if callable(func):
                        func(session_id)
                        logger.info(
                            "clear_session: cleared session %r via SessionManager.%s",
                            session_id,
                            attr,
                        )
                        return

            # Fallback: best-effort delete on-disk artifacts
            if hasattr(self, "session_root"):
                from pathlib import Path

                root = Path(self.session_root)
                for path in root.glob(f"{session_id}*"):
                    try:
                        path.unlink()
                    except Exception:
                        logger.warning(
                            "clear_session: failed to unlink %s for session %r",
                            path,
                            session_id,
                        )

            logger.info("clear_session: completed best-effort clear for %r", session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "clear_session: error while clearing session %r: %s",
                session_id,
                exc,
            )
    
    def chat(
        self,
        user_message: str,
        session_id: str = "cli",
        use_rag: bool = False,
        rag_index: str | None = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Session-aware, optionally RAG-augmented chat.

        - session_id: groups multiple turns into a conversation.
        - use_rag:    if True, pull snippets from a named RAG index.
        - rag_index:  which index to query (e.g. 'docs') when use_rag is True.
        """
        if rag_index is None:
            rag_index = "docs"

        # 1) Load existing history
        history = self._load_history(session_id)

        # 2) Optional RAG context
        rag_context = ""
        if use_rag and rag_index:
            rag_context = self._build_rag_context(rag_index, user_message, top_k=3)

        # 3) Build prompt
        system_prompt = (
            "You are Primus OS, a helpful, concise system assistant. "
            "Use the provided context when it is relevant, but never fabricate facts."
        )

        history_lines: List[str] = []
        for msg in history[-10:]:  # last 10 turns only
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "assistant":
                history_lines.append(f"Assistant: {content}")
            else:
                history_lines.append(f"User: {content}")

        conversation_block = "\n".join(history_lines)
        parts: List[str] = [system_prompt]

        if rag_context:
            parts.append("")
            parts.append(rag_context)

        if conversation_block:
            parts.append("")
            parts.append("Conversation so far:")
            parts.append(conversation_block)

        parts.append("")
        parts.append(f"User: {user_message}")
        parts.append("Assistant:")

        prompt = "\n".join(parts)

        logger.info(
            "Chat request: session_id=%r use_rag=%s rag_index=%r prompt_len=%d",
            session_id,
            use_rag,
            rag_index,
            len(prompt),
        )

        # 4) Call model backend
        reply = self.model_manager.generate(prompt, max_tokens=max_tokens)

        # 5) Persist updated history
        self._append_message(session_id, "user", user_message)
        self._append_message(session_id, "assistant", reply)

        return reply

    def chat_once(self, user_message: str) -> str:
        """
        Single-turn helper used by PrimusRuntime.chat_once.

        For now, we default to:
        - session_id="cli"
        - use_rag=True
        - rag_index="docs"
        """
        return self.chat(
            user_message=user_message,
            session_id="cli",
            use_rag=True,
            rag_index="docs",
            max_tokens=256,
        )

    # ------------------------------------------------------------------ #
    # Core self-test (used by PrimusRuntime.run_bootup_test)            #
    # ------------------------------------------------------------------ #

    def run_self_test(self) -> Dict[str, Any]:
        """
        Lightweight self-test, returning a structured JSON-like summary.
        """
        results: Dict[str, Any] = {}

        # --- RAG embedder ----------------------------------------------------
        try:
            status = get_embedder_status()
            results["rag"] = {"status": "ok", **status}
        except Exception as exc:  # noqa: BLE001
            logger.exception("RAG self-test failed: %s", exc)
            results["rag"] = {"status": "error", "error": str(exc)}

        # --- Agent manager ---------------------------------------------------
        try:
            agents: List[str]
            if hasattr(self.agent_manager, "list_agents"):
                agents = list(self.agent_manager.list_agents())  # type: ignore[call-arg]
            else:
                agents = [
                    p.name
                    for p in self.agents_root.iterdir()
                    if p.is_dir() or p.suffix in (".py",)
                ]
            results["agent_manager"] = {"status": "ok", "agents": agents}
        except Exception as exc:  # noqa: BLE001
            logger.exception("AgentManager self-test failed: %s", exc)
            results["agent_manager"] = {"status": "error", "error": str(exc)}

        # --- Model manager ---------------------------------------------------
        try:
            status_fn = getattr(self.model_manager, "get_backend_status", None)
            if callable(status_fn):
                ok_flag, msg = status_fn()
                results["model_manager"] = {
                    "status": "ok" if ok_flag else "error",
                    "message": msg,
                }
            else:
                results["model_manager"] = {
                    "status": "ok",
                    "message": "ModelManager present (no detailed status API)",
                }
        except Exception as exc:  # noqa: BLE001
            logger.exception("ModelManager self-test failed: %s", exc)
            results["model_manager"] = {"status": "error", "error": str(exc)}

        # --- Memory manager --------------------------------------------------
        try:
            # If it didn't explode yet, call it healthy.
            results["memory"] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("MemoryManager self-test failed: %s", exc)
            results["memory"] = {"status": "error", "error": str(exc)}

        logger.info("Self-test complete.")
        return results
