# core/primus_core.py
# PRIMUS OS — Central Core System

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .agent_manager import AgentManager
from .model_manager import ModelManager
from .memory_manager import MemoryManager, get_memory_manager
from .session_manager import SessionManager
from .subchat_engine import SubchatEngine

logger = logging.getLogger(__name__)


class PrimusCore:
    """
    Central orchestrator for PRIMUS OS.

    Responsibilities:
      - Owns paths & core configuration
      - Manages agents, models, memory, sessions, and subchats
      - Provides simple self-test interface for boot diagnostics
    """

    def __init__(
        self,
        system_root: Optional[str] = None,
        model_path: Optional[str] = None,
        max_subchat_workers: int = 1,
    ) -> None:
        # Resolve system root
        if system_root is None:
            # Default: the repository "System" root (two levels up from this file)
            self.system_root = Path(__file__).resolve().parent.parent
        else:
            self.system_root = Path(system_root).resolve()

        # Derived paths
        self.agents_root = self.system_root / "agents"
        self.sessions_root = self.system_root / "sessions"
        self.memory_root = self.system_root / "memory"

        # Ensure base directories exist
        self.agents_root.mkdir(parents=True, exist_ok=True)
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)

        logger.info("PrimusCore created (system_root=%s)", self.system_root)

        # Initialize subsystems
        self.agent_manager = AgentManager(self.agents_root)
        logger.info("AgentManager initialized.")

        # ModelManager: assumes a local llama.cpp-compatible GGUF model
        # model_path may be None; ModelManager is responsible for handling that.
        self.model_manager = ModelManager(model_path=model_path)
        logger.info("ModelManager initialized.")

        # MemoryManager (JSON-based, shared)
        self.memory_manager: MemoryManager = get_memory_manager(self.memory_root)
        logger.info("MemoryManager initialized.")

        # SessionManager (per-user / per-conversation sessions)
        self.session_manager = SessionManager(
            session_root=self.sessions_root,
            max_history=50,
        )
        logger.info("SessionManager initialized.")

        # Subchat engine (lightweight worker pool for background / threaded chats)
        self.subchat_engine = SubchatEngine(max_workers=max_subchat_workers)
        logger.info("SubchatEngine initialized (max_workers=%s)", max_subchat_workers)

        logger.info("PrimusCore initialization complete.")

    # ------------------------------------------------------------------
    # Runtime lifecycle hooks
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Runtime hook called by PrimusRuntime after construction.

        Currently this is intentionally lightweight and idempotent:
        the heavy lifting (loading models, setting up managers) is
        already done in __init__. This hook is where future
        startup routines or migrations can be added.
        """
        logger.info("PrimusCore.initialize() called - core is ready.")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_agent_manager(self) -> AgentManager:
        return self.agent_manager

    def get_model_manager(self) -> ModelManager:
        return self.model_manager

    def get_memory_manager(self) -> MemoryManager:
        return self.memory_manager

    def get_session_manager(self) -> SessionManager:
        return self.session_manager

    def get_subchat_engine(self) -> SubchatEngine:
        return self.subchat_engine

    # ------------------------------------------------------------------
    # High-level chat APIs (single-turn convenience wrappers)
    # ------------------------------------------------------------------

    def chat_once(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """
        Simple one-shot chat interface used by primus_cli and tests.
        """
        backend = self.model_manager.get_backend()

        # Very simple role-structured messages for llama.cpp chat template
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        logger.info(
            "chat_once invoked with user message length=%d",
            len(message or ""),
        )

        reply = backend.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.info(
            "chat_once completed; reply length=%d",
            len(reply or ""),
        )
        return reply

    # ------------------------------------------------------------------
    # Self-test for boot diagnostics
    # ------------------------------------------------------------------

    def run_self_test(self) -> Dict[str, Any]:
        """
        Lightweight self-test used by PrimusRuntime bootup diagnostics.
        Returns a structured dict describing the health/status of each
        major subsystem.
        """
        results: Dict[str, Any] = {}

        # RAG / embedder health
        try:
            from rag.embedder import get_embedder_status  # type: ignore

            rag_status = get_embedder_status()
            results["rag"] = {"status": "ok", **rag_status}
        except Exception as exc:  # pragma: no cover - diagnostic
            logger.exception("RAG self-test failed: %s", exc)
            results["rag"] = {"status": "error", "error": str(exc)}

        # Agent manager status
        try:
            agents = self.agent_manager.list_agents()
            results["agent_manager"] = {"status": "ok", "agents": agents}
        except Exception as exc:  # pragma: no cover - diagnostic
            logger.exception("AgentManager self-test failed: %s", exc)
            results["agent_manager"] = {"status": "error", "error": str(exc)}

        # Model manager status
        try:
            status = self.model_manager.get_backend_status()
            results["model_manager"] = {"status": "ok", **status}
        except AttributeError:
            # Older/simple ModelManager without status API
            logger.warning("ModelManager has no get_backend_status().")
            results["model_manager"] = {
                "status": "ok",
                "message": "ModelManager present (no detailed status API)",
                "models": [self.model_manager.model_path]
                if getattr(self.model_manager, "model_path", None)
                else [],
            }
        except Exception as exc:  # pragma: no cover - diagnostic
            logger.exception("ModelManager self-test failed: %s", exc)
            results["model_manager"] = {"status": "error", "error": str(exc)}

        # Memory manager check
        try:
            _ = self.memory_manager.read_system_memory()
            results["memory"] = {"status": "ok"}
        except Exception as exc:  # pragma: no cover - diagnostic
            logger.exception("MemoryManager self-test failed: %s", exc)
            results["memory"] = {"status": "error", "error": str(exc)}

        logger.info("Self-test complete.")
        return results


# ----------------------------------------------------------------------
# Factory used by PrimusRuntime and tests
# ----------------------------------------------------------------------


def get_primus_core(
    system_root: Optional[str] = None,
    model_path: Optional[str] = None,
) -> PrimusCore:
    """
    Simple factory used by primus_runtime and CLI.

    system_root: base directory for PRIMUS System (defaults to repo root)
    model_path:  optional override for the GGUF model path
    """
    if system_root is None:
        # Default to the directory containing primus_core, two levels up
        system_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    core = PrimusCore(
        system_root=system_root,
        model_path=model_path,
    )
    logger.info("PrimusCore instance created.")
    return core