# primus_core.py
"""
PRIMUS Core Controller (primus_core.py) - Option C (Full OS controller)

Responsibilities:
- Initialize system components (RAG manager, agent manager, model manager, memory, session manager)
- Provide ingest/search helpers that enforce scope & permissions
- Route messages between agents (permissioned, logged, approval flow)
- Provide system status and a comprehensive self-test routine
- Provide logging for success/failure traces
- Designed to be defensive (graceful fallbacks if components are missing)

Place at:
r"C:\P.R.I.M.U.S OS\System\core\primus_core.py"
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ====== Configuration defaults ======
SYSTEM_ROOT = Path(__file__).resolve().parents[2]  # .../System/core -> parents[2] => .../System
LOG_DIR = SYSTEM_ROOT / "core" / "system_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primus_core.log"

# Concurrency: how many agent-to-agent collaborations can run concurrently
DEFAULT_MAX_PARALLEL_AGENT_INTERACTIONS = 2

# Approval token prefix
_APPROVAL_PREFIX = "PRIMUS-APPROVAL-"

# ====== Setup logging ======
logger = logging.getLogger("primus_core")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
fh.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(fh)
# Also log to console for convenience (when running terminal tests)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)


# ====== Defensive imports for pluggable components ======
try:
    from rag.rag_manager import RAGManager  # user-created rag_manager.py
except Exception:
    RAGManager = None
    logger.warning("RAGManager not available; RAG functionality will be limited.")

try:
    from core.agent_manager import AgentManager
except Exception:
    AgentManager = None
    logger.warning("AgentManager not available; agent registration will be limited.")

try:
    from core.model_manager import ModelManager
except Exception:
    ModelManager = None
    logger.warning("ModelManager not available; model management will be limited.")

try:
    from core.subchat_loader import SubchatLoader
    from core.subchat_security import SubchatSecurity
    from core.subchat_state import SubchatStateManager
    from core.subchat_engine import SubchatEngine
except Exception:
    SubchatLoader = None
    SubchatSecurity = None
    SubchatStateManager = None
    SubchatEngine = None
    logger.warning("Subchat components not available; subchat support disabled.")

try:
    from core.memory import MemoryManager
except Exception:
    MemoryManager = None
    logger.warning("MemoryManager not available; memory features will be limited.")

try:
    from core.session_manager import SessionManager, SessionNotFound
except Exception:
    SessionManager = None
    SessionNotFound = None  # type: ignore
    logger.warning("SessionManager not available; sessions will be limited.")


# ====== Core controller class ======
class PrimusCore:
    def __init__(self, max_parallel_interactions: int = DEFAULT_MAX_PARALLEL_AGENT_INTERACTIONS):
        self.system_root = SYSTEM_ROOT
        self.max_parallel_interactions = max_parallel_interactions

        # Components (filled in initialize)
        self.rag: Optional[Any] = None
        self.agent_manager: Optional[Any] = None
        self.model_manager: Optional[Any] = None
        self.memory: Optional[Any] = None
        self.session_manager: Optional[Any] = None

        # Subchat
        self.subchat_security: Optional[Any] = None
        self.subchat_loader: Optional[Any] = None
        self.subchat_state_manager: Optional[Any] = None
        self.subchat_engine: Optional[Any] = None

        # Agent interaction control
        self._interaction_lock = threading.BoundedSemaphore(self.max_parallel_interactions)
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Basic registry of agent permissions (agent_name -> dict)
        # Permissions fields: {"can_read_global_rag": bool, "can_write_own_rag": bool, "can_contact_agents": bool}
        self.agent_permissions: Dict[str, Dict[str, Any]] = {}

        logger.info("PrimusCore instance created.")

    # -------------------------
    # Initialization / Shutdown
    # -------------------------
    def initialize(self) -> Dict[str, Any]:
        """
        Initialize all available subsystems. Returns a dict describing statuses.
        """
        logger.info("Initializing PrimusCore subsystems...")
        statuses = {}

        # RAG manager
        try:
            if RAGManager:
                self.rag = RAGManager(system_root=str(self.system_root))
                statuses["rag"] = {"status": "ok"}
                logger.info("RAGManager initialized.")
            else:
                statuses["rag"] = {"status": "missing"}
        except Exception as e:
            statuses["rag"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize RAGManager.")

        # Agent manager
        try:
            if AgentManager:
                try:
                    self.agent_manager = AgentManager(system_root=str(self.system_root))
                except TypeError:
                    # Fallback for constructors that do not accept system_root
                    self.agent_manager = AgentManager()
                statuses["agent_manager"] = {"status": "ok"}
                logger.info("AgentManager initialized.")
            else:
                statuses["agent_manager"] = {"status": "missing"}
        except Exception as e:
            statuses["agent_manager"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize AgentManager.")

        # Model manager
        try:
            if ModelManager:
                self.model_manager = ModelManager(system_root=str(self.system_root))
                statuses["model_manager"] = {"status": "ok"}
                logger.info("ModelManager initialized.")
            else:
                statuses["model_manager"] = {"status": "missing"}
        except Exception as e:
            statuses["model_manager"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize ModelManager.")

        # Memory manager
        try:
            if MemoryManager:
                try:
                    self.memory = MemoryManager(system_root=str(self.system_root))
                except TypeError:
                    self.memory = MemoryManager()
                statuses["memory"] = {"status": "ok"}
                logger.info("MemoryManager initialized.")
            else:
                statuses["memory"] = {"status": "missing"}
        except Exception as e:
            statuses["memory"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize MemoryManager.")

        # Session manager
        try:
            if SessionManager:
                try:
                    self.session_manager = SessionManager(system_root=str(self.system_root))
                except TypeError:
                    self.session_manager = SessionManager()
                statuses["session_manager"] = {"status": "ok"}
                logger.info("SessionManager initialized.")
            else:
                statuses["session_manager"] = {"status": "missing"}
        except Exception as e:
            statuses["session_manager"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize SessionManager.")

        # Subchat subsystem
        try:
            if SubchatLoader and SubchatSecurity and SubchatStateManager:
                self.subchat_security = SubchatSecurity()
                self.subchat_state_manager = SubchatStateManager()
                self.subchat_loader = SubchatLoader(
                    security=self.subchat_security,
                    state_manager=self.subchat_state_manager,
                )
                if SubchatEngine:
                    self.subchat_engine = SubchatEngine()
                count = len(self.subchat_loader.list_ids()) if self.subchat_loader else 0
                statuses["subchats"] = {"status": "ok", "count": count}
                logger.info("Subchat subsystem initialized (%s subchats discovered).", count)
            else:
                statuses["subchats"] = {"status": "missing"}
        except Exception as e:
            statuses["subchats"] = {"status": "error", "error": str(e)}
            logger.exception("Failed to initialize subchat subsystem.")

        # Load agent permissions if available (persisted file)
        permissions_file = self.system_root / "configs" / "agent_permissions.json"
        if permissions_file.exists():
            try:
                with open(permissions_file, "r", encoding="utf-8") as f:
                    self.agent_permissions = json.load(f)
                statuses["permissions"] = {"status": "loaded"}
                logger.info("Agent permissions loaded from disk.")
            except Exception as e:
                statuses["permissions"] = {"status": "error", "error": str(e)}
                logger.exception("Failed to load agent permissions file.")
        else:
            # initialize empty and persist later when registering agents
            self.agent_permissions = {}
            statuses["permissions"] = {"status": "none"}

        logger.info("PrimusCore initialization complete.")
        return statuses

    def shutdown(self):
        """Graceful shutdown hooks for components (best-effort)."""
        logger.info("Shutting down PrimusCore subsystems...")
        # If components provide a close/stop method, call them
        for comp_name in ("rag", "agent_manager", "model_manager", "memory", "session_manager"):
            comp = getattr(self, comp_name)
            try:
                if comp and hasattr(comp, "close"):
                    comp.close()
                    logger.info(f"Closed component: {comp_name}")
            except Exception:
                logger.exception(f"Error closing {comp_name}")
        logger.info("Shutdown complete.")

    # -------------------------
    # Permission & registration helpers
    # -------------------------
    def register_agent(self, agent_name: str, permissions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Register agent with basic permission set. This does NOT auto-create agent code,
        it simply records permissions and persists them.
        """
        with self._lock:
            if permissions is None:
                permissions = {
                    "can_read_global_rag": False,
                    "can_write_own_rag": True,
                    "can_contact_agents": False,
                    "can_read_other_agents_rag": False,
                }
            self.agent_permissions[agent_name] = permissions
            self._persist_permissions()
            logger.info(f"Registered agent '{agent_name}' with permissions: {permissions}")
            return {"status": "ok", "agent": agent_name, "permissions": permissions}

    def update_agent_permissions(self, agent_name: str, permissions: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if agent_name not in self.agent_permissions:
                return {"status": "error", "error": "agent_not_registered"}
            self.agent_permissions[agent_name].update(permissions)
            self._persist_permissions()
            logger.info(f"Updated permissions for '{agent_name}': {permissions}")
            return {"status": "ok", "agent": agent_name, "permissions": self.agent_permissions[agent_name]}

    def _persist_permissions(self):
        try:
            permissions_file = self.system_root / "configs" / "agent_permissions.json"
            permissions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(permissions_file, "w", encoding="utf-8") as f:
                json.dump(self.agent_permissions, f, indent=2)
            logger.debug("Persisted agent permissions to disk.")
        except Exception:
            logger.exception("Failed to persist agent permissions.")

    # -------------------------
    # RAG operations (ingest/search)
    # -------------------------
    def ingest(self, path: str, scope: str = "system", agent_name: Optional[str] = None,
               chunk_size: int = 500, overlap: int = 50, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Ingest documents into a given scope:
            - scope = "system" -> system/global rag
            - scope = "agent"  -> agent's private rag (agent_name required)
        Enforces permissions and logs results.
        """
        logger.info(f"Ingest requested: path={path}, scope={scope}, agent={agent_name}")
        try:
            # Validate permission
            if scope == "agent":
                if not agent_name:
                    return {"status": "error", "error": "agent_name_required_for_agent_scope"}
                perms = self.agent_permissions.get(agent_name, {})
                if not perms.get("can_write_own_rag", False):
                    return {"status": "error", "error": "permission_denied"}

            if self.rag:
                if scope == "system":
                    res = self.rag.ingest_folder(path=path, scope="system",
                                                 chunk_size=chunk_size, overlap=overlap, model=model)
                else:
                    res = self.rag.ingest_folder(path=path, scope=f"agent:{agent_name}",
                                                 chunk_size=chunk_size, overlap=overlap, model=model)
                logger.info("Ingest result: %s", res)
                return {"status": "ok", "result": res}
            else:
                logger.error("RAG manager not available.")
                return {"status": "error", "error": "rag_manager_unavailable"}
        except Exception as e:
            logger.exception("Ingest failed.")
            return {"status": "error", "error": str(e)}

    def search_rag(self, query: str, scope: str = "system", agent_name: Optional[str] = None,
                   topk: int = 5) -> Dict[str, Any]:
        """
        Search RAG with permission enforcement.
        scope values:
          - "system" -> system/global
          - "agent" -> agent's private store (agent_name required)
          - "all" -> merge system + agent as allowed (agent_name optional)
        Returns topk hits with metadata.
        """
        logger.info(f"Search requested: query='{query}' scope={scope} agent={agent_name} topk={topk}")
        try:
            if not self.rag:
                return {"status": "error", "error": "rag_manager_unavailable"}

            # Permission checks
            if scope == "agent":
                if not agent_name:
                    return {"status": "error", "error": "agent_name_required_for_agent_scope"}
                perms = self.agent_permissions.get(agent_name, {})
                if not perms.get("can_read_global_rag", True) and agent_name is None:
                    return {"status": "error", "error": "permission_denied"}

            # Delegation to rag manager
            if scope == "system":
                hits = self.rag.search(query=query, scope="system", topk=topk)
            elif scope == "agent":
                hits = self.rag.search(query=query, scope=f"agent:{agent_name}", topk=topk)
            elif scope == "all":
                # gather system + agent (where allowed)
                sys_hits = self.rag.search(query=query, scope="system", topk=topk)
                agg_hits = sys_hits
                if agent_name:
                    agg_hits += self.rag.search(query=query, scope=f"agent:{agent_name}", topk=topk)
                # simple dedupe by metadata text (could be improved)
                seen_texts = set()
                dedup = []
                for h in agg_hits:
                    txt = json.dumps(h.get("metadata", {}).get("text", "")) if h.get("metadata") else ""
                    if txt not in seen_texts:
                        dedup.append(h)
                        seen_texts.add(txt)
                hits = dedup[:topk]
            else:
                return {"status": "error", "error": "unknown_scope"}

            logger.info("Search returned %d hits", len(hits))
            return {"status": "ok", "hits": hits}
        except Exception as e:
            logger.exception("Search failed.")
            return {"status": "error", "error": str(e)}

    def rag_index_path(self, name: str, path: str | Path, recursive: bool = False) -> None:
        """
        Public wrapper used by the CLI to index a path into a named RAG index.
        Thin wrapper around the underlying RAG indexer / manager.
        """

        logger.info(
            "RAG index request: name=%r path=%r recursive=%s",
            name,
            str(path),
            recursive,
        )

        rm = getattr(self, "rag_manager", None)
        if rm is not None and hasattr(rm, "index_path"):
            rm.index_path(name=name, path=str(path), recursive=recursive)
            return

        if hasattr(self, "rag_indexer") and getattr(self, "rag_indexer") is not None:
            self.rag_indexer.index_path(name=name, path=str(path), recursive=recursive)
            return

        logger.warning(
            "rag_index_path called but no RAG indexer/manager is configured "
            "(name=%r, path=%r)",
            name,
            path,
        )

    def rag_retrieve(
        self,
        name: str,
        query: str,
        top_k: int = 3,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Public helper to retrieve top-k documents from a named RAG index.
        Thin wrapper around the underlying RAG retriever / manager.
        """

        logger.info(
            "RAG retrieve request: index=%r query_len=%d top_k=%d",
            name,
            len(query),
            top_k,
        )

        rm = getattr(self, "rag_manager", None)
        if rm is not None and hasattr(rm, "retrieve"):
            return rm.retrieve(name=name, query=query, top_k=top_k)

        if hasattr(self, "rag_retriever") and getattr(self, "rag_retriever") is not None:
            return self.rag_retriever.retrieve(name=name, query=query, top_k=top_k)

        logger.warning(
            "rag_retrieve called but no RAG retriever/manager is configured "
            "(index=%r)",
            name,
        )
        return []

    # -------------------------
    # Agent -> Agent routing (permissioned + approval)
    # -------------------------
    def route_message(self, src_agent: str, dst_agent: str, payload: Dict[str, Any],
                      require_approval: bool = True, timeout: int = 60) -> Dict[str, Any]:
        """
        Route a message from src_agent to dst_agent subject to permissions and approvals.
        If require_approval is True, an approval token is returned which must be confirmed by the human (external)
        to actually deliver the message. This protects against autonomous agent-to-agent leakage.

        Returns:
            - immediate delivered result (if approval not required)
            - pending token (if approval required)
        """
        logger.info("Routing message from %s -> %s (require_approval=%s)", src_agent, dst_agent, require_approval)

        # Basic permission check
        src_perms = self.agent_permissions.get(src_agent, {})
        dst_perms = self.agent_permissions.get(dst_agent, {})
        if not src_perms or not dst_perms:
            logger.warning("One or both agents not registered.")
            return {"status": "error", "error": "agent_not_registered"}

        if not src_perms.get("can_contact_agents", False):
            logger.warning("Source agent not allowed to contact other agents.")
            return {"status": "error", "error": "src_not_allowed_to_contact_agents"}

        if not dst_perms.get("can_contact_agents", True):
            logger.warning("Destination agent not allowed to receive agent messages.")
            return {"status": "error", "error": "dst_not_allowed_to_receive_messages"}

        # Approval flow
        if require_approval:
            token = f"{_APPROVAL_PREFIX}{int(time.time()*1000)}-{src_agent}-{dst_agent}"
            with self._lock:
                self._pending_approvals[token] = {
                    "src": src_agent,
                    "dst": dst_agent,
                    "payload": payload,
                    "status": "pending",
                    "created": time.time(),
                }
            logger.info("Message pending approval: token=%s", token)
            # Caller (human/UI) should call confirm_approval(token, approve=True/False)
            return {"status": "pending_approval", "token": token}
        else:
            # deliver immediately (best-effort) by invoking dispatcher/agent bridge if present
            try:
                if self.agent_manager and hasattr(self.agent_manager, "call_agent_method"):
                    # common pattern: agent_manager.call_agent_method(dst_agent, method, payload)
                    result = self.agent_manager.call_agent_method(dst_agent, "handle_message", payload)
                    logger.info("Delivered message immediately; result=%s", result)
                    return {"status": "delivered", "result": result}
                else:
                    logger.warning("Agent manager cannot deliver messages (missing method).")
                    return {"status": "error", "error": "delivery_mechanism_unavailable"}
            except Exception as e:
                logger.exception("Error delivering message immediately.")
                return {"status": "error", "error": str(e)}

    def confirm_approval(self, token: str, approve: bool) -> Dict[str, Any]:
        """
        Human/UI confirms or rejects a pending agent->agent message.
        If approved, the message is delivered (synchronously) and the delivery result returned.
        """
        with self._lock:
            pending = self._pending_approvals.get(token)
            if not pending:
                logger.warning("Approval token not found: %s", token)
                return {"status": "error", "error": "token_not_found"}

            pending["status"] = "approved" if approve else "rejected"
            pending["confirmed_at"] = time.time()

        if not approve:
            logger.info("Approval token rejected: %s", token)
            return {"status": "rejected", "token": token}

        # Proceed to deliver
        src = pending["src"]
        dst = pending["dst"]
        payload = pending["payload"]

        try:
            if self.agent_manager and hasattr(self.agent_manager, "call_agent_method"):
                result = self.agent_manager.call_agent_method(dst, "handle_message", payload)
                logger.info("Delivered approved message; token=%s result=%s", token, result)
                with self._lock:
                    pending["delivered"] = True
                    pending["result"] = result
                return {"status": "delivered", "result": result}
            else:
                logger.warning("Agent manager cannot deliver approved messages.")
                return {"status": "error", "error": "delivery_mechanism_unavailable"}
        except Exception as e:
            logger.exception("Approved delivery failed.")
            return {"status": "error", "error": str(e)}

    # -------------------------
    # Self-test routine
    # -------------------------
    def run_self_test(self) -> Dict[str, Any]:
        """
        Run a quick self-test across key components:
         - rag ingest + search smoke test (if RAG manager present)
         - agent manager reachable
         - model manager reachable
         - memory manager reachable
        Returns a dict with statuses and short logs.
        """
        logger.info("Running Primus self-test...")
        summary = {"timestamp": time.time(), "results": {}}

        # RAG smoke test
        try:
            if self.rag:
                # prefer to run a lightweight check (list scopes + basic search)
                scopes = self.rag.list_scopes() if hasattr(self.rag, "list_scopes") else None
                summary["results"]["rag"] = {"status": "ok", "scopes": scopes}
            else:
                summary["results"]["rag"] = {"status": "missing"}
        except Exception as e:
            logger.exception("RAG self-test failed.")
            summary["results"]["rag"] = {"status": "error", "error": str(e)}

        # Agent manager
        try:
            if self.agent_manager:
                agents = self.agent_manager.list_agents() if hasattr(self.agent_manager, "list_agents") else None
                summary["results"]["agent_manager"] = {"status": "ok", "agents": agents}
            else:
                summary["results"]["agent_manager"] = {"status": "missing"}
        except Exception as e:
            logger.exception("AgentManager self-test failed.")
            summary["results"]["agent_manager"] = {"status": "error", "error": str(e)}

        # Model manager
        try:
            if self.model_manager:
                models = self.model_manager.list_models() if hasattr(self.model_manager, "list_models") else None
                summary["results"]["model_manager"] = {"status": "ok", "models": models}
            else:
                summary["results"]["model_manager"] = {"status": "missing"}
        except Exception as e:
            logger.exception("ModelManager self-test failed.")
            summary["results"]["model_manager"] = {"status": "error", "error": str(e)}

        # Memory manager
        try:
            if self.memory:
                summary["results"]["memory"] = {"status": "ok"}
            else:
                summary["results"]["memory"] = {"status": "missing"}
        except Exception as e:
            logger.exception("Memory self-test failed.")
            summary["results"]["memory"] = {"status": "error", "error": str(e)}

        logger.info("Self-test complete.")
        return summary

    # -------------------------
    # Subchat helpers (integration surface for runtime/CLI)
    # -------------------------
    def list_subchats(self) -> List[str]:
        if not self.subchat_loader:
            return []
        return self.subchat_loader.list_ids()

    def create_subchat(
        self,
        owner: str,
        label: str,
        is_private: bool = False,
        allowed_agents: Optional[List[str]] = None,
    ) -> str:
        if not self.subchat_loader:
            raise RuntimeError("Subchat loader unavailable")
        return self.subchat_loader.create_subchat(
            owner=owner,
            label=label,
            is_private=is_private,
            allowed_agents=allowed_agents or [],
        )

    def get_subchat_info(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        if not self.subchat_security:
            return None
        return self.subchat_security.get_subchat_info(subchat_id)

    def model_status_check(self) -> Tuple[bool, str]:
        if not self.model_manager:
            return False, "ModelManager unavailable"
        try:
            return self.model_manager.model_status_check()
        except Exception as exc:
            logger.exception("ModelManager status check failed: %s", exc)
            return False, str(exc)

    # -------------------------
    # Status / Utilities
    # -------------------------
    def get_status(self) -> Dict[str, Any]:
        """Return summarized status about the system and components."""
        status = {
            "system_root": str(self.system_root),
            "rag": "present" if self.rag else "missing",
            "agent_manager": "present" if self.agent_manager else "missing",
            "model_manager": "present" if self.model_manager else "missing",
            "memory": "present" if self.memory else "missing",
            "session_manager": "present" if self.session_manager else "missing",
            "agent_permissions_count": len(self.agent_permissions),
            "max_parallel_interactions": self.max_parallel_interactions,
        }
        logger.debug("Status requested: %s", status)
        return status

    # -------------------------
    # Chat APIs (unified entrypoint)
    # -------------------------
    def chat(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        use_rag: bool = False,
        rag_index: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Unified chat entrypoint for PrimusCore with optional session history and RAG context.

        The method centralizes chat behavior for all front-ends by:
        - loading prior turns when a session id is supplied (creating the session skeleton if
          missing),
        - optionally retrieving RAG snippets when `use_rag` and `rag_index` are provided,
        - building a single prompt that includes a short system primer, optional RAG context,
          any conversation history, and the latest user message,
        - delegating response generation to the configured ModelManager, and
        - persisting the new turn back into the session when a session id is in use.
        """

        if not self.model_manager:
            raise RuntimeError("ModelManager not initialized; cannot generate responses.")

        history: List[Dict[str, Any]] = []
        active_session_id: Optional[str] = None

        if session_id:
            if not self.session_manager:
                raise RuntimeError("SessionManager not initialized; session-based chat unavailable.")
            active_session_id, history = self._load_or_initialize_session(session_id)

        rag_snippets = self._retrieve_rag_context(user_message, use_rag=use_rag, rag_index=rag_index)
        rag_context = self._build_rag_context(rag_snippets)
        system_prompt = self._load_persona_text()
        prompt = self._build_chat_prompt(
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
            rag_context=rag_context,
        )
        logger.info(
            "Chat request: session_id=%r use_rag=%s rag_index=%r prompt_len=%d",
            active_session_id or session_id,
            use_rag,
            rag_index,
            len(prompt),
        )

        try:
            reply_text = self.model_manager.generate(prompt, max_tokens=max_tokens)
        except Exception as exc:
            logger.exception("Model generation failed")
            raise RuntimeError(f"Model generation failed: {exc}") from exc

        if self.session_manager and active_session_id:
            self._append_message(active_session_id, role="user", content=user_message)
            self._append_message(active_session_id, role="assistant", content=reply_text)

        return reply_text

    def chat_once(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        use_rag: bool = False,
        rag_index: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Convenience wrapper primarily used by PrimusRuntime for single-turn chats. Delegates to
        :meth:`chat` without adding extra logic.
        """
        return self.chat(
            user_message=user_message,
            session_id=session_id,
            use_rag=use_rag,
            rag_index=rag_index,
            max_tokens=max_tokens,
        )

    def _retrieve_rag_context(
        self,
        query: str,
        use_rag: bool,
        rag_index: Optional[str],
        topk: int = 3,
    ) -> List[Tuple[str, str]]:
        """Retrieve lightweight RAG snippets when enabled and available."""

        if not (use_rag and rag_index and self.rag and hasattr(self.rag, "search")):
            return []

        snippets: List[Tuple[str, str]] = []
        try:
            hits = self.rag.search(query=query, scope=rag_index, topk=topk)
            for hit in hits:
                metadata = hit.get("metadata", {}) if isinstance(hit, dict) else {}
                path = metadata.get("path") or metadata.get("source_file") or metadata.get("source") or rag_index
                text = metadata.get("text") or hit.get("preview") or hit.get("text") or ""
                preview = text[:240] + ("..." if len(text) > 240 else "")
                score_val = hit.get("score") if isinstance(hit, dict) else None
                score_val = score_val if score_val is not None else hit.get("distance") if isinstance(hit, dict) else None
                score = f"{score_val:.4f}" if isinstance(score_val, (int, float)) else "?"
                snippets.append((score, f"{path}: {preview}"))
        except Exception:
            logger.warning("RAG retrieval failed or index missing; proceeding without context.", exc_info=True)

        return snippets

    def _build_rag_context(self, rag_snippets: List[Tuple[str, str]]) -> str:
        """Format retrieved RAG snippets into a labeled context block."""

        if not rag_snippets:
            return ""

        rag_block_lines: List[str] = []
        for score, snippet in rag_snippets:
            rag_block_lines.append(f"- ({score}) {snippet}")
        return "\n".join(rag_block_lines)

    def _load_persona_text(self) -> str:
        """Return the fixed Primus persona / system instruction block."""

        default_persona = (
            "You are Primus OS, a helpful, concise system assistant. Prefer to admit when "
            "information is missing rather than guessing. When RAG context is provided, use it "
            "carefully: quote or summarize relevant snippets, but do not invent configuration or "
            "undocumented capabilities. If the context does not answer the question, say so "
            "explicitly."
        )
        return default_persona

    def _build_chat_prompt(
        self,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_message: str,
        rag_context: Optional[str],
    ) -> str:
        """Compose the final prompt with persona, optional RAG context, history, and the new turn."""

        prompt_parts: List[str] = [
            "===== PRIMUS PERSONA =====",
            system_prompt.strip(),
            "==========================",
        ]

        if rag_context:
            prompt_parts.extend(
                [
                    "===== RAG CONTEXT (may be relevant) =====",
                    rag_context.strip(),
                    "==========================================",
                ]
            )

        filtered_history: List[Dict[str, Any]] = []
        for msg in history:
            text = msg.get("text") or msg.get("content") or ""
            if text:
                filtered_history.append({"role": msg.get("role", "user"), "content": text})

        if filtered_history:
            filtered_history = filtered_history[-10:]
            prompt_parts.append("Conversation so far:")
            for msg in filtered_history:
                role_label = "Assistant" if msg.get("role") == "assistant" else "User"
                prompt_parts.append(f"{role_label}: {msg.get('content', '')}")

        prompt_parts.extend(
            [
                "===== New message =====",
                f"User: {user_message}",
                "Assistant:",
            ]
        )

        return "\n".join(prompt_parts)

    def _load_or_initialize_session(self, session_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Load session history or create a new session when missing using SessionManager."""

        if not self.session_manager:
            raise RuntimeError("SessionManager not initialized")

        try:
            if hasattr(self.session_manager, "ensure_session"):
                session_ref = self.session_manager.ensure_session(session_id, owner="user", privacy="private")
            else:
                session_ref = self.session_manager.load_session(session_id)
            history = list(session_ref.get("messages", [])) if isinstance(session_ref, dict) else []
            active_session_id = session_ref.get("id", session_id) if isinstance(session_ref, dict) else session_id
            return active_session_id, history
        except Exception as exc:
            should_init = SessionNotFound is None or isinstance(exc, SessionNotFound)
            if not should_init:
                logger.exception("Failed to load session %s; continuing without history.", session_id)
                return session_id, []

        try:
            if hasattr(self.session_manager, "create_session"):
                session_ref = self.session_manager.create_session(
                    title=session_id, owner="user", privacy="private", session_id=session_id
                )
                session_id_resolved = session_ref.get("id", session_id) if isinstance(session_ref, dict) else session_id
                return session_id_resolved, []
        except Exception:
            logger.exception("Failed to initialize new session %s", session_id)

        return session_id, []

    def _load_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Helper to load a session history from SessionManager, if available.

        Expected shape: list of {"role": "user"|"assistant", "content": str}
        """

        sm = getattr(self, "session_manager", None)
        if sm is None:
            return []

        try:
            history = sm.load_history(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("load_history failed for %r: %s", session_id, exc)
            return []

        return history or []

    def _append_message(self, session_id: str, role: str, content: str) -> None:
        """
        Helper to append a single message into a session, if the SessionManager
        exposes a suitable write API. Fails softly if no such API exists.
        """

        sm = getattr(self, "session_manager", None)
        if sm is None:
            return

        msg = {"role": role, "content": content}

        append_fn = getattr(sm, "append_message", None)
        if callable(append_fn):
            try:
                append_fn(session_id, msg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("append_message failed for %r: %s", session_id, exc)
            return

        add_fn = getattr(sm, "add_message", None)
        if callable(add_fn):
            try:
                add_fn(session_id, role=role, who=role, text=content)
            except Exception as exc:  # noqa: BLE001
                logger.warning("add_message failed for %r: %s", session_id, exc)
            return

        if hasattr(sm, "load_history") and hasattr(sm, "save_history"):
            try:
                history = sm.load_history(session_id) or []
                history.append({"role": role, "text": content})
                sm.save_history(session_id, history)
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_history fallback failed for %r: %s", session_id, exc)
            return

        logger.debug(
            "SessionManager has no append/write API; skipping write for session %r",
            session_id,
        )

    def list_sessions(self) -> List[str]:
        """
        Return a sorted list of known session IDs.
        """

        if not self.session_manager:
            return []

        sessions: List[str] = []
        try:
            if hasattr(self.session_manager, "list_sessions"):
                raw_sessions = self.session_manager.list_sessions()
                for entry in raw_sessions:
                    if isinstance(entry, dict):
                        sid = entry.get("id")
                        if sid:
                            sessions.append(str(sid))
                    elif isinstance(entry, str):
                        sessions.append(entry)
            else:
                session_dir = self.system_root / "system" / "sessions"
                if session_dir.exists():
                    sessions = [p.stem for p in session_dir.glob("*.json") if p.is_file()]
        except Exception:
            logger.exception("Failed to list sessions.")
            return []

        sessions = sorted(set(sessions))
        logger.info("Listing sessions: %r", sessions)
        return sessions

    def get_session_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return chat history for a session as a list of message dicts like
        {"role": "user"|"assistant", "content": "..."}.

        If limit is set, return only the most recent N messages.
        """

        messages = self._load_history(session_id)

        if limit is not None:
            messages = messages[-limit:]

        history = [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("text", msg.get("content", "")),
            }
            for msg in messages
            if isinstance(msg, dict)
        ]
        logger.info("Loaded session history for %r (len=%d)", session_id, len(history))
        return history

    def clear_session(self, session_id: str) -> None:
        """
        Delete/clear all history for the given session ID.

        If the session does not exist, this is a no-op.
        """

        if not self.session_manager:
            logger.info("No session manager available; nothing to clear for %r", session_id)
            return

        cleared = False
        try:
            if hasattr(self.session_manager, "delete_session"):
                self.session_manager.delete_session(session_id)
                cleared = True
            else:
                session_path = self.system_root / "system" / "sessions" / f"{session_id}.json"
                if session_path.exists():
                    session_path.unlink()
                    cleared = True
        except Exception:
            logger.exception("Failed to clear session %r", session_id)
            return

        if cleared:
            if hasattr(self.session_manager, "_cache") and session_id in getattr(self.session_manager, "_cache", {}):
                try:
                    del self.session_manager._cache[session_id]
                except Exception:
                    logger.debug("Failed to evict %r from session cache", session_id)
            logger.info("Cleared session %r", session_id)
        else:
            logger.info("No session %r to clear", session_id)

    # -------------------------
    # Simple helper: allow an agent to request a RAG search across allowed scopes
    # -------------------------
    def agent_search(self, agent_name: str, query: str, topk: int = 5) -> Dict[str, Any]:
        """
        Agent-facing helper: search system RAG + agent's own RAG if permitted by policies.
        """
        logger.info("Agent '%s' requested search: %s", agent_name, query)
        perms = self.agent_permissions.get(agent_name, {})
        allowed_scopes = []
        if perms.get("can_read_global_rag", False):
            allowed_scopes.append("system")
        if perms.get("can_read_own_rag", True):
            allowed_scopes.append(f"agent:{agent_name}")

        aggregate = []
        for scope in allowed_scopes:
            try:
                if self.rag:
                    hits = self.rag.search(query=query, scope=scope, topk=topk)
                    aggregate.extend(hits)
            except Exception:
                logger.exception("Agent search failed for scope: %s", scope)

        return {"status": "ok", "hits": aggregate[:topk]}

# -------------------------
# Module-level singleton for convenience
# -------------------------
_primus_singleton: Optional[PrimusCore] = None


def get_primus_core(singleton: bool = True) -> PrimusCore:
    global _primus_singleton
    if singleton and _primus_singleton:
        return _primus_singleton
    pc = PrimusCore()
    if singleton:
        _primus_singleton = pc
    return pc


# Simple CLI for quick tests (when run directly)
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="PRIMUS Core CLI")
    parser.add_argument("--self-test", action="store_true", help="Run quick self-test")
    parser.add_argument("--status", action="store_true", help="Print status")
    args = parser.parse_args()

    primus = get_primus_core()
    init_status = primus.initialize()
    print("Initialize:", json.dumps(init_status, indent=2))

    if args.status:
        print(json.dumps(primus.get_status(), indent=2))

    if args.self_test:
        st = primus.run_self_test()
        print("Self-test:", json.dumps(st, indent=2))


if __name__ == "__main__":
    _cli()