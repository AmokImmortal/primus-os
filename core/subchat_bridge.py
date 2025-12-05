subchat_bridge.py

Connects Subchat Engine <-> PRIMUS Core Engine and Agent System.

Location (example):
C:\P.R.I.M.U.S OS\System\core\subchat_bridge.py

Responsibilities:
- Register and unregister subchats with the core.
- Route messages from PRIMUS/Core -> subchat and subchat -> Core/Agents.
- Enforce basic permission checks and logging hooks (delegates to higher-level guards).
- Serialize / persist minimal subchat routing metadata.
- Provide a thin abstraction so other core modules (agent_manager, session_manager, engine)
  can send/receive messages without importing subchat internals.

Design goals:
- Minimal dependencies (only standard library).
- Defensive error handling and clear return values.
- Pluggable hooks for permission checks and logging (callable attributes).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid
import time

ROOT = Path(__file__).resolve().parents[1]  # .../core
DATA_DIR = ROOT / "subchat_data"
META_FILE = DATA_DIR / "subchat_registry.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Type aliases for hooks
PermissionHook = Callable[[str, str, Dict[str, Any]], bool]
LoggingHook = Callable[[str, Dict[str, Any]], None]
MessageHandler = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class SubchatBridge:
    """
    Central registry + router for subchats.
    """

    def __init__(self):
        # subchat_id -> metadata
        self._registry: Dict[str, Dict[str, Any]] = {}
        # subchat_id -> inbound handler (callable) for messages targeted at that subchat
        self._handlers: Dict[str, MessageHandler] = {}
        self._lock = threading.RLock()

        # Hooks (replaceable by higher-level modules)
        self.permission_hook: Optional[PermissionHook] = None
        self.logging_hook: Optional[LoggingHook] = None
        # fallback handler when messages are routed to core/agents
        self.core_router: Optional[MessageHandler] = None

        # Load persisted registry if present
        self._load_registry()

    # ---------------------------
    # Persistence
    # ---------------------------
    def _load_registry(self):
        try:
            if META_FILE.exists():
                with open(META_FILE, "r", encoding="utf-8") as f:
                    self._registry = json.load(f)
        except Exception:
            # ignore errors but keep empty registry
            self._registry = {}

    def _save_registry(self):
        try:
            with open(META_FILE, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=2, ensure_ascii=False)
        except Exception:
            # best-effort; higher-level logger should record failures
            pass

    # ---------------------------
    # Registration
    # ---------------------------
    def register_subchat(self, name: str, owner: str, meta: Optional[Dict[str, Any]] = None) -> str:
        """
        Register a new subchat and return its id.

        name: human readable name
        owner: owning agent or 'primus' for main user
        meta: optional metadata (e.g., 'private': True)
        """
        with self._lock:
            sid = str(uuid.uuid4())
            entry = {
                "id": sid,
                "name": name,
                "owner": owner,
                "created_at": time.time(),
                "meta": meta or {}
            }
            self._registry[sid] = entry
            self._save_registry()
            self._log_event("register", entry)
            return sid

    def unregister_subchat(self, subchat_id: str) -> bool:
        with self._lock:
            if subchat_id in self._registry:
                entry = self._registry.pop(subchat_id)
                self._save_registry()
                # remove handler if present
                self._handlers.pop(subchat_id, None)
                self._log_event("unregister", entry)
                return True
            return False

    def list_subchats(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._registry.values())

    def get_subchat(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._registry.get(subchat_id)

    # ---------------------------
    # Handler management
    # ---------------------------
    def attach_handler(self, subchat_id: str, handler: MessageHandler) -> bool:
        """
        Attach a callable that will receive messages for this subchat.
        The handler should accept (from_id, payload) and return a dict response.
        """
        with self._lock:
            if subchat_id not in self._registry:
                return False
            self._handlers[subchat_id] = handler
            self._log_event("attach_handler", {"id": subchat_id})
            return True

    def detach_handler(self, subchat_id: str):
        with self._lock:
            self._handlers.pop(subchat_id, None)
            self._log_event("detach_handler", {"id": subchat_id})

    # ---------------------------
    # Routing & Permissions
    # ---------------------------
    def _check_permission(self, actor: str, target_subchat: str, payload: Dict[str, Any]) -> bool:
        """
        Use the permission_hook if provided, else allow by default for safety
        (higher-level modules should set permission_hook to enforce rules).
        """
        if self.permission_hook:
            try:
                return bool(self.permission_hook(actor, target_subchat, payload))
            except Exception:
                return False
        # default permissive behaviour (substitute a restrictive default in production)
        return True

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        if self.logging_hook:
            try:
                self.logging_hook(event_type, data)
            except Exception:
                pass

    def send_to_subchat(self, from_actor: str, subchat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Primary entrypoint: route a message from an actor (PRIMUS or agent) to a subchat.

        from_actor: e.g., "primus", "agent:FileAgent"
        subchat_id: destination subchat id
        payload: dict with arbitrary keys, expected to contain "type" and "body"

        Returns a dict response:
           {"status": "ok", "response": {...}} or {"status":"error", "error": "..."}
        """
        timestamp = time.time()
        self._log_event("send_to_subchat_attempt", {
            "from": from_actor, "to": subchat_id, "payload": payload, "ts": timestamp
        })

        with self._lock:
            if subchat_id not in self._registry:
                return {"status": "error", "error": "subchat_not_found"}

            # permission check
            if not self._check_permission(from_actor, subchat_id, payload):
                self._log_event("permission_denied", {"from": from_actor, "to": subchat_id})
                return {"status": "error", "error": "permission_denied"}

            # call handler if exists
            handler = self._handlers.get(subchat_id)
            if handler:
                try:
                    resp = handler(from_actor, payload)
                    self._log_event("send_to_subchat_success", {"from": from_actor, "to": subchat_id})
                    return {"status": "ok", "response": resp}
                except Exception as e:
                    self._log_event("send_to_subchat_error", {"error": str(e)})
                    return {"status": "error", "error": "handler_error", "detail": str(e)}
            else:
                # No handler attached: route to core_router as fallback
                if self.core_router:
                    try:
                        resp = self.core_router(subchat_id, payload)
                        self._log_event("send_to_subchat_core_routed", {"subchat_id": subchat_id})
                        return {"status": "ok", "response": resp}
                    except Exception as e:
                        self._log_event("core_route_error", {"error": str(e)})
                        return {"status": "error", "error": "core_route_error", "detail": str(e)}
                return {"status": "error", "error": "no_handler"}

    def send_from_subchat(self, subchat_id: str, to_actor: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called by subchat handlers when they need to send messages to Core or Agents.

        subchat_id: origin subchat id
        to_actor: e.g., "primus", "agent:SearchAgent", or "core"
        payload: message dict
        """
        timestamp = time.time()
        self._log_event("send_from_subchat_attempt", {
            "from_subchat": subchat_id, "to": to_actor, "payload": payload, "ts": timestamp
        })

        # Basic permission check: ensure subchat exists and is allowed
        with self._lock:
            if subchat_id not in self._registry:
                return {"status": "error", "error": "subchat_not_found"}

        # If target is core or unspecified, call core_router
        if self.core_router:
            try:
                resp = self.core_router(to_actor, {"from_subchat": subchat_id, **payload})
                self._log_event("send_from_subchat_core_routed", {"from": subchat_id, "to": to_actor})
                return {"status": "ok", "response": resp}
            except Exception as e:
                self._log_event("send_from_subchat_core_error", {"error": str(e)})
                return {"status": "error", "error": "core_router_error", "detail": str(e)}
        else:
            return {"status": "error", "error": "no_core_router"}

    # ---------------------------
    # Utility Helpers
    # ---------------------------
    def set_permission_hook(self, hook: PermissionHook):
        """Hook signature: (actor, target_subchat, payload) -> bool"""
        self.permission_hook = hook

    def set_logging_hook(self, hook: LoggingHook):
        """Hook signature: (event_type, data) -> None"""
        self.logging_hook = hook

    def set_core_router(self, router: MessageHandler):
        """
        Router signature: (destination, payload) -> dict
        Destination might be an agent id, "primus", or other core targets.
        """
        self.core_router = router

    # ---------------------------
    # Convenience wrappers
    # ---------------------------
    def create_private_subchat(self, name: str, owner: str, password_hash: Optional[str] = None) -> str:
        """
        Convenience to create a private subchat. The permission hook is expected to enforce privacy.
        """
        meta = {"private": True}
        if password_hash:
            meta["password_hash"] = password_hash
        return self.register_subchat(name=name, owner=owner, meta=meta)

    # ---------------------------
    # Shutdown / cleanup
    # ---------------------------
    def shutdown(self):
        # persist registry
        self._save_registry()
        # detach handlers
        with self._lock:
            self._handlers.clear()
        self._log_event("shutdown", {"registry_count": len(self._registry)})