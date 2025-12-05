#!/usr/bin/env python3
"""
core/primus_core.py

Central coordinator for PRIMUS OS subsystems.

Responsibilities (v1 offline core):
- Wire together:
    - AgentManager
    - ModelManager (local llama.cpp backend)
    - MemoryManager (JSON-based)
    - SessionManager
    - SubchatLoader / SubchatSecurity / SubchatEngine
    - Optional permissions / RAG (if present)
- Provide a simple initialize() hook that:
    - Brings subsystems online
    - Returns a structured status dict
- Provide helpers used by primus_runtime and primus_cli:
    - list_subchats()
    - create_subchat()
    - get_subchat_info()
    - model_status_check()
    - run_self_test()
- Expose get_primus_core(singleton=True) for a shared instance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("primus_core")

# ---------------------------------------------------------------------------
# Safe imports for subsystems
# ---------------------------------------------------------------------------

# Agent manager
try:
    from .agent_manager import AgentManager
except Exception:  # noqa: BLE001
    AgentManager = None  # type: ignore[assignment]
    logger.warning("AgentManager not available; agent functionality will be limited.")

# Model manager (llama.cpp backend wrapper)
try:
    from .model_manager import ModelManager
except Exception:  # noqa: BLE001
    ModelManager = None  # type: ignore[assignment]
    logger.warning("ModelManager not available; model backend will be unavailable.")

# Memory manager (JSON-based)
try:
    from .memory_manager import MemoryManager
except Exception:  # noqa: BLE001
    MemoryManager = None  # type: ignore[assignment]
    logger.warning("MemoryManager not available; memory subsystem disabled.")

# Session manager
try:
    from .session_manager import SessionManager
except Exception:  # noqa: BLE001
    SessionManager = None  # type: ignore[assignment]
    logger.warning("SessionManager not available; session tracking disabled.")

# Subchat components
try:
    from .subchat_loader import SubchatLoader
except Exception:  # noqa: BLE001
    SubchatLoader = None  # type: ignore[assignment]
    logger.warning("SubchatLoader not available; subchat registry disabled.")

try:
    from .subchat_security import SubchatSecurity
except Exception:  # noqa: BLE001
    SubchatSecurity = None  # type: ignore[assignment]
    logger.warning("SubchatSecurity not available; subchat security disabled.")

try:
    from .subchat_engine import SubchatEngine
except Exception:  # noqa: BLE001
    SubchatEngine = None  # type: ignore[assignment]
    logger.warning("SubchatEngine not available; subchat execution disabled.")

# Permissions (optional)
try:
    from . import permissions as permissions_module
except Exception:  # noqa: BLE001
    permissions_module = None
    logger.warning("permissions module not available; permission checks disabled.")

# Optional RAG manager (may not be present yet)
try:
    from .rag_manager import RAGManager  # type: ignore[import]
except Exception:  # noqa: BLE001
    RAGManager = None  # type: ignore[assignment]
    logger.warning("RAGManager not available; RAG functionality will be limited.")


# ---------------------------------------------------------------------------
# PrimusCore
# ---------------------------------------------------------------------------


class PrimusCore:
    """
    Central PRIMUS OS core coordinator.

    This class wires subsystems together and exposes a small set of helpers
    used by the runtime/CLI. It is intentionally conservative and offline-first.
    """

    def __init__(self, system_root: Optional[Path] = None):
        self.system_root: Path = system_root or Path(__file__).resolve().parents[1]

        # Subsystem handles (may remain None if import/initialization fails)
        self.agent_manager: Optional[Any] = None
        self.model_manager: Optional[Any] = None
        self.memory_manager: Optional[Any] = None
        self.session_manager: Optional[Any] = None
        self.subchat_loader: Optional[Any] = None
        self.subchat_security: Optional[Any] = None
        self.subchat_engine: Optional[Any] = None
        self.permissions: Optional[Any] = None
        self.rag_manager: Optional[Any] = None

        logger.info("PrimusCore created (system_root=%s)", self.system_root)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> Dict[str, Any]:
        """
        Initialize subsystems and return a structured status dict.

        This should be safe to call multiple times; repeated calls
        re-use existing managers when possible.
        """
        status: Dict[str, Any] = {
            "rag": {"status": "missing"},
            "agent_manager": {"status": "missing"},
            "model_manager": {"status": "missing"},
            "memory": {"status": "missing"},
            "session_manager": {"status": "missing"},
            "subchats": {"status": "missing", "count": 0},
            "permissions": {"status": "missing"},
        }

        # RAG (optional)
        if RAGManager is not None:
            try:
                if self.rag_manager is None:
                    self.rag_manager = RAGManager(self.system_root)
                status["rag"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize RAGManager: %s", exc)
                status["rag"] = {"status": "error", "error": str(exc)}
        else:
            status["rag"] = {"status": "missing"}

        # Agent manager
        if AgentManager is not None:
            try:
                if self.agent_manager is None:
                    agents_dir = self.system_root / "agents"
                    self.agent_manager = AgentManager(agents_dir)
                agents = getattr(self.agent_manager, "list_agents", lambda: [])()
                status["agent_manager"] = {"status": "ok", "agents": agents}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize AgentManager: %s", exc)
                status["agent_manager"] = {"status": "error", "error": str(exc)}
        else:
            status["agent_manager"] = {"status": "missing"}

        # Model manager
        if ModelManager is not None:
            try:
                if self.model_manager is None:
                    self.model_manager = ModelManager()
                ok, msg = self.model_status_check()
                status["model_manager"] = {
                    "status": "ok" if ok else "degraded",
                    "models": getattr(self.model_manager, "list_models", lambda: [])(),
                }
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize ModelManager: %s", exc)
                status["model_manager"] = {"status": "error", "error": str(exc)}
        else:
            status["model_manager"] = {"status": "missing"}

        # Memory manager
        if MemoryManager is not None:
            try:
                if self.memory_manager is None:
                    self.memory_manager = MemoryManager()
                status["memory"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize MemoryManager: %s", exc)
                status["memory"] = {"status": "error", "error": str(exc)}
        else:
            status["memory"] = {"status": "missing"}

        # Session manager
        if SessionManager is not None:
            try:
                if self.session_manager is None:
                    self.session_manager = SessionManager()
                status["session_manager"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize SessionManager: %s", exc)
                status["session_manager"] = {"status": "error", "error": str(exc)}
        else:
            status["session_manager"] = {"status": "missing"}

        # Subchats
        subchat_count = 0
        if SubchatLoader is not None and SubchatSecurity is not None and SubchatEngine is not None:
            try:
                if self.subchat_security is None:
                    self.subchat_security = SubchatSecurity(self.system_root)
                if self.subchat_loader is None:
                    self.subchat_loader = SubchatLoader(self.system_root, self.subchat_security)
                if self.subchat_engine is None:
                    self.subchat_engine = SubchatEngine(max_workers=1)

                list_fn = getattr(self.subchat_loader, "list_subchats", None)
                if callable(list_fn):
                    subchats = list_fn()
                    subchat_count = len(subchats)
                status["subchats"] = {"status": "ok", "count": subchat_count}
                logger.info("Subchat subsystem initialized (%d subchats discovered).", subchat_count)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize subchat subsystem: %s", exc)
                status["subchats"] = {"status": "error", "error": str(exc), "count": subchat_count}
        else:
            status["subchats"] = {"status": "missing", "count": 0}

        # Permissions (optional)
        if permissions_module is not None:
            try:
                if hasattr(permissions_module, "PermissionsManager"):
                    if self.permissions is None:
                        self.permissions = permissions_module.PermissionsManager()  # type: ignore[attr-defined]
                    status["permissions"] = {"status": "ok"}
                else:
                    status["permissions"] = {"status": "none"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to initialize permissions: %s", exc)
                status["permissions"] = {"status": "error", "error": str(exc)}
        else:
            status["permissions"] = {"status": "none"}

        logger.info("PrimusCore initialization complete.")
        return status

    # ------------------------------------------------------------------
    # Subchat helpers (used by runtime/CLI)
    # ------------------------------------------------------------------

    def list_subchats(self) -> List[Any]:
        """Return a list of subchat metadata, or an empty list if unavailable."""
        if self.subchat_loader is None:
            return []
        list_fn = getattr(self.subchat_loader, "list_subchats", None)
        if not callable(list_fn):
            return []
        return list_fn()

    def create_subchat(self, owner: str, label: str, is_private: bool = False) -> str:
        """
        Create a new subchat and return its ID.

        Delegates to SubchatLoader / controller.
        """
        if self.subchat_loader is None:
            raise RuntimeError("Subchat subsystem not initialized.")
        create_fn = getattr(self.subchat_loader, "create_subchat", None)
        if not callable(create_fn):
            raise RuntimeError("SubchatLoader.create_subchat is not available.")
        return create_fn(owner=owner, label=label, is_private=is_private)

    def get_subchat_info(self, subchat_id: str) -> Dict[str, Any]:
        """Return metadata for a given subchat, or {} if unavailable."""
        if self.subchat_loader is None:
            return {}
        info_fn = getattr(self.subchat_loader, "get_subchat_info", None)
        if not callable(info_fn):
            return {}
        return info_fn(subchat_id)

    # ------------------------------------------------------------------
    # Model backend helpers
    # ------------------------------------------------------------------

    def model_status_check(self) -> Tuple[bool, str]:
        """
        Return (ok, message) describing the model backend status.

        Used by primus_runtime bootup tests.
        """
        if self.model_manager is None:
            return False, "ModelManager not initialized"

        # Prefer a dedicated status API if present
        status_fn = getattr(self.model_manager, "backend_status", None)
        if callable(status_fn):
            try:
                ok, msg = status_fn()
                return bool(ok), str(msg)
            except Exception as exc:  # noqa: BLE001
                logger.exception("ModelManager.backend_status failed: %s", exc)
                return False, f"backend_status error: {exc}"

        # Fallback to has_backend() if available
        has_fn = getattr(self.model_manager, "has_backend", None)
        if callable(has_fn):
            try:
                ok = bool(has_fn())
                return ok, "Model backend available" if ok else "Model backend missing"
            except Exception as exc:  # noqa: BLE001
                logger.exception("ModelManager.has_backend failed: %s", exc)
                return False, f"has_backend error: {exc}"

        # Final fallback
        return True, "ModelManager present (no detailed status API)"

    # ------------------------------------------------------------------
    # Self-test
    # ------------------------------------------------------------------

    def run_self_test(self) -> Dict[str, Any]:
        """
        Lightweight core self-test.

        Returns a dict summarizing the status of key subsystems.
        This is intentionally simple and offline-only.
        """
        results: Dict[str, Any] = {
            "timestamp": __import__("time").time(),
            "results": {
                "rag": {"status": "missing"},
                "agent_manager": {"status": "missing"},
                "model_manager": {"status": "missing"},
                "memory": {"status": "missing"},
            },
        }

        # RAG
        results["results"]["rag"]["status"] = "ok" if self.rag_manager is not None else "missing"

        # AgentManager
        if self.agent_manager is not None:
            try:
                agents = getattr(self.agent_manager, "list_agents", lambda: [])()
                results["results"]["agent_manager"] = {"status": "ok", "agents": agents}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Self-test: AgentManager failed: %s", exc)
                results["results"]["agent_manager"] = {"status": "error", "error": str(exc)}
        else:
            results["results"]["agent_manager"] = {"status": "missing"}

        # ModelManager
        if self.model_manager is not None:
            try:
                ok, msg = self.model_status_check()
                models = getattr(self.model_manager, "list_models", lambda: [])()
                results["results"]["model_manager"] = {
                    "status": "ok" if ok else "degraded",
                    "message": msg,
                    "models": models,
                }
            except Exception as exc:  # noqa: BLE001
                logger.exception("Self-test: ModelManager failed: %s", exc)
                results["results"]["model_manager"] = {"status": "error", "error": str(exc)}
        else:
            results["results"]["model_manager"] = {"status": "missing"}

        # Memory
        if self.memory_manager is not None:
            try:
                _ = self.memory_manager.read_system_memory()  # type: ignore[union-attr]
                results["results"]["memory"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Self-test: MemoryManager failed: %s", exc)
                results["results"]["memory"] = {"status": "error", "error": str(exc)}
        else:
            results["results"]["memory"] = {"status": "missing"}

        logger.info("Self-test complete.")
        return results


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_core_singleton: Optional[PrimusCore] = None


def get_primus_core(singleton: bool = True) -> PrimusCore:
    """
    Return a PrimusCore instance.

    - singleton=True (default): return a shared process-local instance.
    - singleton=False: return a new PrimusCore every call.
    """
    global _core_singleton

    if not singleton:
        return PrimusCore()

    if _core_singleton is None:
        _core_singleton = PrimusCore()

    return _core_singleton


__all__ = ["PrimusCore", "get_primus_core"]