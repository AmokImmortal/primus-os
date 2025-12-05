# /core/subchat_engine.py
"""
Subchat Engine - central orchestrator for subchat lifecycle, routing, security and sandboxing.

Responsibilities:
- Manage subchat creation, start/stop, and destruction
- Route messages between subchats and agents (via controller/router)
- Enforce access control and security checks before routing
- Emit and handle lifecycle/events through the events module
- Provide a simple threaded runtime loop for message processing

This file is designed to integrate with the other core subchat components:
 - subchat_runtime
 - subchat_controller
 - subchat_api
 - subchat_security
 - subchat_sandbox
 - subchat_events
 - subchat_state
 - subchat_lifecycle

If any of those modules are missing, lightweight local fallbacks are used so the engine remains importable.
"""

import threading
import time
import uuid
import logging
from queue import Queue, Empty
from typing import Dict, Any, Optional, Callable

# Simple logger configured for core
logger = logging.getLogger("subchat_engine")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [subchat_engine] %(levelname)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# Try to import related modules; provide minimal fallbacks if missing
try:
    from core import subchat_runtime as runtime_mod  # type: ignore
except Exception:
    runtime_mod = None

try:
    from core import subchat_controller as controller_mod  # type: ignore
except Exception:
    controller_mod = None

try:
    from core import subchat_api as api_mod  # type: ignore
except Exception:
    api_mod = None

try:
    from core import subchat_security as security_mod  # type: ignore
except Exception:
    security_mod = None

try:
    from core import subchat_sandbox as sandbox_mod  # type: ignore
except Exception:
    sandbox_mod = None

try:
    from core import subchat_events as events_mod  # type: ignore
except Exception:
    events_mod = None

try:
    from core import subchat_state as state_mod  # type: ignore
except Exception:
    state_mod = None

try:
    from core import subchat_lifecycle as lifecycle_mod  # type: ignore
except Exception:
    lifecycle_mod = None


# Lightweight fallback classes (used only when the real module is missing)
class _FallbackController:
    def route(self, origin_id: str, dest_id: str, message: dict) -> None:
        logger.debug("FallbackController.route called - no-op")

class _FallbackSecurity:
    def check_send(self, origin_id: str, dest_id: str, message: dict) -> bool:
        # Allow by default
        return True

class _FallbackEvents:
    def emit(self, name: str, payload: dict) -> None:
        logger.debug("FallbackEvents.emit %s %s", name, payload)

class _FallbackState:
    def __init__(self):
        self.store = {}
    def get(self, key, default=None):
        return self.store.get(key, default)
    def set(self, key, val):
        self.store[key] = val

class _FallbackSandbox:
    def is_in_sandbox(self, subchat_id: str) -> bool:
        return False
    def apply_sandbox_rules(self, subchat_id: str, message: dict) -> dict:
        return message

# Resolve actual modules or fallbacks
Controller = getattr(controller_mod, "SubchatController", _FallbackController)
Security = getattr(security_mod, "SubchatSecurity", _FallbackSecurity)
Events = getattr(events_mod, "SubchatEvents", _FallbackEvents)
State = getattr(state_mod, "SubchatState", _FallbackState)
Sandbox = getattr(sandbox_mod, "SubchatSandbox", _FallbackSandbox)


class SubchatEngine:
    """
    Central engine to manage subchat operations.
    """

    def __init__(self, max_workers: int = 1):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._queue: "Queue[dict]" = Queue()
        self._subchats: Dict[str, Dict[str, Any]] = {}  # id -> metadata
        self._controller = Controller() if Controller is not _FallbackController else Controller()
        self._security = Security() if Security is not _FallbackSecurity else Security()
        self._events = Events() if Events is not _FallbackEvents else Events()
        if State is not _FallbackState:
            try:
                self._state = State(subchat_id="__engine__")
            except TypeError:
                self._state = State()
        else:
            self._state = State()
        self._sandbox = Sandbox() if Sandbox is not _FallbackSandbox else Sandbox()
        self._max_workers = max_workers
        self._worker_threads = []
        self._stop_event = threading.Event()

        logger.info("SubchatEngine initialized (max_workers=%s)", max_workers)

    # -------------------------
    # Lifecycle: start / stop
    # -------------------------
    def start(self):
        if self._running:
            logger.warning("Engine already running")
            return
        self._running = True
        self._stop_event.clear()
        # Start a single dispatcher thread and optional worker threads
        self._thread = threading.Thread(target=self._dispatch_loop, name="SubchatEngine.Dispatcher", daemon=True)
        self._thread.start()
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"SubchatEngine.Worker-{i}", daemon=True)
            t.start()
            self._worker_threads.append(t)
        logger.info("SubchatEngine started")

    def stop(self):
        if not self._running:
            logger.warning("Engine not running")
            return
        self._running = False
        self._stop_event.set()
        # enqueue sentinel to wake workers
        for _ in range(len(self._worker_threads) + 1):
            self._queue.put({"type": "engine.shutdown"})
        if self._thread:
            self._thread.join(timeout=2.0)
        for t in self._worker_threads:
            t.join(timeout=2.0)
        self._worker_threads = []
        logger.info("SubchatEngine stopped")

    # -------------------------
    # Subchat management
    # -------------------------
    def create_subchat(self, name: str, owner: Optional[str] = None, private: bool = False, sandboxed: bool = False) -> str:
        subchat_id = str(uuid.uuid4())
        meta = {
            "id": subchat_id,
            "name": name,
            "owner": owner,
            "private": bool(private),
            "sandboxed": bool(sandboxed),
            "created_at": time.time()
        }
        self._subchats[subchat_id] = meta
        self._events.emit("subchat.created", meta)
        logger.info("Created subchat %s (%s)", name, subchat_id)
        return subchat_id

    def delete_subchat(self, subchat_id: str) -> bool:
        if subchat_id not in self._subchats:
            logger.warning("delete_subchat: unknown id %s", subchat_id)
            return False
        meta = self._subchats.pop(subchat_id)
        self._events.emit("subchat.deleted", {"id": subchat_id, **meta})
        logger.info("Deleted subchat %s", subchat_id)
        return True

    def list_subchats(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._subchats)

    # -------------------------
    # Message routing (public API)
    # -------------------------
    def send_message(self, origin_id: str, dest_id: str, payload: dict):
        """
        Public method to queue a message for routing.
        payload may contain arbitrary fields: {type, content, metadata...}
        """
        envelope = {
            "type": "message.route",
            "from": origin_id,
            "to": dest_id,
            "payload": payload,
            "ts": time.time()
        }
        self._queue.put(envelope)
        logger.debug("Enqueued message from %s to %s", origin_id, dest_id)

    # -------------------------
    # Internal loops
    # -------------------------
    def _dispatch_loop(self):
        logger.debug("Dispatch loop started")
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                if not isinstance(item, dict):
                    continue
                itype = item.get("type")

                if itype == "engine.shutdown":
                    logger.debug("Received engine.shutdown")
                    break

                if itype == "message.route":
                    # simple dispatch to worker queue (workers consume same queue)
                    logger.debug("Dispatching message %s", item)
                    # put back into queue for workers (they'll pick it up)
                    self._queue.put(item)
                    # small sleep to allow worker threads to acquire
                    time.sleep(0.01)
                else:
                    logger.debug("Unhandled dispatch item type: %s", itype)
            except Exception as e:
                logger.exception("Error in dispatch loop: %s", e)

        logger.debug("Dispatch loop exiting")

    def _worker_loop(self):
        logger.debug("Worker loop started")
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                if not isinstance(item, dict):
                    continue
                itype = item.get("type")

                if itype == "engine.shutdown":
                    logger.debug("Worker received shutdown")
                    break

                if itype == "message.route":
                    self._process_route(item)
                else:
                    logger.debug("Worker unhandled item: %s", itype)
            except Exception as e:
                logger.exception("Error in worker loop: %s", e)

        logger.debug("Worker loop exiting")

    # -------------------------
    # Routing & processing
    # -------------------------
    def _process_route(self, envelope: dict):
        origin = envelope.get("from")
        dest = envelope.get("to")
        payload = envelope.get("payload", {})

        logger.debug("Processing route %s -> %s", origin, dest)

        # Basic validation: known subchats or allow special destinations (e.g., "broadcast")
        if dest != "broadcast" and dest not in self._subchats:
            logger.warning("Destination unknown: %s", dest)
            self._events.emit("route.failed", {"reason": "unknown_dest", "dest": dest, "origin": origin})
            return

        # Security check
        try:
            allowed = self._security.check_send(origin, dest, payload)
        except Exception as e:
            logger.exception("Security check failed: %s", e)
            allowed = False

        if not allowed:
            logger.info("Security blocked message from %s to %s", origin, dest)
            self._events.emit("route.blocked", {"origin": origin, "dest": dest, "payload": payload})
            return

        # Sandbox transformation if applicable
        try:
            if self._sandbox.is_in_sandbox(dest):
                payload = self._sandbox.apply_sandbox_rules(dest, payload)
                logger.debug("Applied sandbox rules for %s", dest)
        except Exception as e:
            logger.exception("Sandbox processing failed: %s", e)
            self._events.emit("sandbox.error", {"subchat": dest, "error": str(e)})

        # Use controller/router to deliver message (controller is responsible for actual delivery semantics)
        try:
            self._controller.route(origin, dest, payload)
            self._events.emit("route.success", {"origin": origin, "dest": dest, "payload": payload})
            logger.info("Routed message %s -> %s", origin, dest)
        except Exception as e:
            logger.exception("Controller routing failed: %s", e)
            self._events.emit("route.failed", {"origin": origin, "dest": dest, "error": str(e)})

    # -------------------------
    # Utilities
    # -------------------------
    def on_event(self, event_name: str, handler: Callable[[dict], None]):
        """
        Register a local event handler by wrapping the events module emit/listen if provided.
        This will attempt to attach a listener to the events module if it supports it, otherwise
        it will register a simple local handler.
        """
        if hasattr(self._events, "register"):
            try:
                self._events.register(event_name, handler)
                return
            except Exception:
                logger.debug("Events module register failed, falling back to local handler")

        # fallback: store handler in state (very simple)
        handlers = self._state.get("_local_event_handlers", {})
        handlers.setdefault(event_name, []).append(handler)
        self._state.set("_local_event_handlers", handlers)

    def emit_local(self, event_name: str, payload: dict):
        """
        Emit an event locally. This tries the events module first, then local handlers.
        """
        try:
            self._events.emit(event_name, payload)
        except Exception:
            handlers = self._state.get("_local_event_handlers", {})
            for h in handlers.get(event_name, []):
                try:
                    h(payload)
                except Exception:
                    logger.exception("Local handler failed for event %s", event_name)

    # -------------------------
    # Convenience helpers for integration
    # -------------------------
    def create_and_start_subchat(self, name: str, owner: Optional[str] = None, **kwargs) -> str:
        subchat_id = self.create_subchat(name=name, owner=owner, **kwargs)
        # event for lifecycle start
        self._events.emit("subchat.started", {"id": subchat_id})
        return subchat_id


# Simple module-level engine instance for convenience
_engine: Optional[SubchatEngine] = None


def get_engine(max_workers: int = 1) -> SubchatEngine:
    global _engine
    if _engine is None:
        _engine = SubchatEngine(max_workers=max_workers)
    return _engine


# Allow running as a simple smoke-test when executed directly
if __name__ == "__main__":
    e = get_engine(max_workers=1)
    e.start()
    sid = e.create_subchat("demo", owner="local", private=False)
    sid2 = e.create_subchat("other", owner="local", private=False)
    e.send_message(sid, sid2, {"type": "text", "content": "hello from demo"})
    time.sleep(1.0)
    e.stop()