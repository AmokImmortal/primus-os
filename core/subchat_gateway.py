"""
/core/subchat_gateway.py

Unified gateway for SubChat subsystem.
Provides a simple, robust interface to:
 - create / load / unload subchat sessions
 - register / discover subchat components
 - route inputs -> subchat engines and collect outputs
 - basic permission checks and logging hooks

Placement:
C:\P.R.I.M.U.S OS\System\core\subchat_gateway.py
"""

import os
import json
import uuid
import time
import threading
from typing import Dict, Any, Optional, Callable, List

ROOT = Path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBCHAT_DIR = os.path.join(ROOT, "sub_chats")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(SUBCHAT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

_DEFAULT_SESSION_TTL = 60 * 60 * 24  # 24 hours default TTL


def _now_ts() -> float:
    return time.time()


def _write_log(name: str, payload: str) -> None:
    fname = os.path.join(LOG_DIR, f"subchat_gateway.log")
    try:
        with open(fname, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {name} | {payload}\n")
    except Exception:
        pass  # best-effort logging


class SubChatSession:
    """Represents one subchat runtime/session record (lightweight)."""

    def __init__(self, session_id: Optional[str] = None, owner: Optional[str] = None, meta: Optional[Dict[str, Any]] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.owner = owner or "unknown"
        self.created_at = _now_ts()
        self.last_active = self.created_at
        self.meta = meta or {}
        self.lock = threading.RLock()
        self.active = True
        self.ttl = _DEFAULT_SESSION_TTL

    def touch(self):
        with self.lock:
            self.last_active = _now_ts()

    def is_expired(self) -> bool:
        return (_now_ts() - self.last_active) > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner": self.owner,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "meta": self.meta,
            "active": self.active,
            "ttl": self.ttl,
        }


class SubChatGateway:
    """
    Gateway orchestrator for subchat subsystem.
    Responsibilities:
      - Manage lightweight session lifecycle
      - Route inputs to registered subchat handlers
      - Provide simple persistence + logging
      - Enforce basic permission hooks via callbacks
    """

    def __init__(self):
        # registered subchat handlers: name -> callable(input, session_meta) -> output
        self.handlers: Dict[str, Callable[[str, Dict[str, Any]], Dict[str, Any]]] = {}
        # active sessions
        self.sessions: Dict[str, SubChatSession] = {}
        # optional permission callback: (session, handler_name, action, payload) -> bool
        self.permission_cb: Optional[Callable[[SubChatSession, str, str, Any], bool]] = None
        # persistence file for minimal registry
        self.registry_file = os.path.join(SUBCHAT_DIR, "registry.json")
        self._load_registry()
        # housekeeping thread for session cleanup
        self._housekeeper = threading.Thread(target=self._housekeeping_loop, daemon=True)
        self._housekeeper_stop = threading.Event()
        self._housekeeper.start()
        _write_log("gateway_init", "SubChatGateway initialized")

    # --------------------------
    # Registry persistence
    # --------------------------
    def _load_registry(self):
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # currently only store handler names (metadata)
                self.registered_meta = data.get("handlers", {})
            except Exception:
                self.registered_meta = {}
        else:
            self.registered_meta = {}

    def _save_registry(self):
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump({"handlers": self.registered_meta}, f, indent=2)
        except Exception:
            _write_log("registry_save_error", f"Could not save {self.registry_file}")

    # --------------------------
    # Handler registration
    # --------------------------
    def register_handler(self, name: str, handler_callable: Callable[[str, Dict[str, Any]], Dict[str, Any]], meta: Optional[Dict[str, Any]] = None):
        """
        Register a subchat handler.
        handler_callable should accept (input_text:str, session_meta:dict) and return dict with at least {"output": str}
        """
        if not callable(handler_callable):
            raise ValueError("handler_callable must be callable")
        self.handlers[name] = handler_callable
        self.registered_meta[name] = meta or {}
        self._save_registry()
        _write_log("register_handler", f"Registered handler '{name}'")

    def unregister_handler(self, name: str):
        if name in self.handlers:
            self.handlers.pop(name, None)
        if name in self.registered_meta:
            self.registered_meta.pop(name, None)
            self._save_registry()
        _write_log("unregister_handler", f"Unregistered handler '{name}'")

    def list_handlers(self) -> List[str]:
        return list(self.handlers.keys())

    # --------------------------
    # Permission hook
    # --------------------------
    def set_permission_callback(self, cb: Callable[[SubChatSession, str, str, Any], bool]):
        """
        cb(session, handler_name, action, payload) -> bool
        action examples: "invoke", "read", "write"
        """
        self.permission_cb = cb

    def _check_permission(self, session: SubChatSession, handler_name: str, action: str, payload: Any = None) -> bool:
        if self.permission_cb is None:
            return True  # default allow
        try:
            return bool(self.permission_cb(session, handler_name, action, payload))
        except Exception as e:
            _write_log("permission_cb_error", str(e))
            return False

    # --------------------------
    # Session lifecycle
    # --------------------------
    def create_session(self, owner: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, ttl: Optional[int] = None) -> SubChatSession:
        s = SubChatSession(owner=owner, meta=meta)
        if ttl:
            s.ttl = ttl
        self.sessions[s.session_id] = s
        _write_log("session_create", json.dumps(s.to_dict()))
        return s

    def get_session(self, session_id: str) -> Optional[SubChatSession]:
        s = self.sessions.get(session_id)
        if s and not s.is_expired():
            return s
        return None

    def close_session(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if not s:
            return False
        s.active = False
        try:
            del self.sessions[session_id]
        except KeyError:
            pass
        _write_log("session_close", session_id)
        return True

    # --------------------------
    # Routing
    # --------------------------
    def route_input(self, handler_name: str, session_id: str, input_text: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main routing method. Returns handler response dict.
        Performs permission checks, sanitization hooks, logging.
        """
        extra = extra or {}
        session = self.sessions.get(session_id)
        if session is None or not session.active:
            return {"status": "error", "error": "invalid_session"}

        session.touch()

        if handler_name not in self.handlers:
            return {"status": "error", "error": "handler_not_found"}

        # permission check
        if not self._check_permission(session, handler_name, "invoke", {"input": input_text, "extra": extra}):
            return {"status": "error", "error": "permission_denied"}

        handler = self.handlers[handler_name]
        _write_log("route_input", f"session={session_id} handler={handler_name} input_len={len(input_text)}")
        try:
            # call handler (best-effort protection)
            resp = handler(input_text, {"session": session.to_dict(), **extra})
            # ensure dict response
            if not isinstance(resp, dict):
                resp = {"output": str(resp)}
            # log output size
            _write_log("handler_output", f"session={session_id} handler={handler_name} out_len={len(str(resp.get('output','')))}")
            return {"status": "ok", "response": resp}
        except Exception as e:
            _write_log("handler_error", f"{handler_name} exception: {e}")
            return {"status": "error", "error": "handler_exception", "detail": str(e)}

    # --------------------------
    # Utilities
    # --------------------------
    def discover(self) -> Dict[str, Any]:
        return {
            "handlers": list(self.registered_meta.keys()),
            "active_sessions": len(self.sessions),
        }

    def shutdown(self, reason: Optional[str] = None):
        _write_log("gateway_shutdown", reason or "no reason")
        # Mark all sessions inactive
        for sid in list(self.sessions.keys()):
            try:
                self.sessions[sid].active = False
                del self.sessions[sid]
            except Exception:
                pass
        # stop housekeeper
        self._housekeeper_stop.set()
        if self._housekeeper.is_alive():
            self._housekeeper.join(timeout=1)

    # --------------------------
    # Housekeeping
    # --------------------------
    def _housekeeping_loop(self):
        while not self._housekeeper_stop.is_set():
            try:
                now = _now_ts()
                expired = [sid for sid, s in list(self.sessions.items()) if s.is_expired()]
                for sid in expired:
                    _write_log("session_expire", sid)
                    try:
                        del self.sessions[sid]
                    except Exception:
                        pass
                time.sleep(30)
            except Exception:
                time.sleep(5)

# Provide a module-level singleton gateway for ease-of-use
_gateway_singleton: Optional[SubChatGateway] = None


def get_subchat_gateway() -> SubChatGateway:
    global _gateway_singleton
    if _gateway_singleton is None:
        _gateway_singleton = SubChatGateway()
    return _gateway_singleton