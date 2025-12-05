"""
subchat_integrator.py

Single integration layer that connects:
 - Subchat Manager / Runtime / Router / Bridge
 - Agent Manager
 - Permissions / Security / Logging / Messaging

Responsibilities:
 - Initialize and wire components together
 - Provide high-level APIs to create/start/stop subchats
 - Route messages between subchats and agents with permission checks
 - Centralized interaction logging
 - Graceful shutdown and health checks

This file intentionally keeps logic defensive (try/except) so it can be dropped into
the existing PRIMUS codebase and will degrade gracefully if optional modules are absent.
"""

from __future__ import annotations

import os
import time
import json
import threading
from typing import Any, Dict, Optional, List

# Defensive imports: many modules live in core/ or project root depending on earlier steps.
try:
    from core.subchat_manager import SubchatManager
except Exception:
    SubchatManager = None

try:
    from core.subchat_runtime import SubchatRuntime
except Exception:
    SubchatRuntime = None

try:
    from core.subchat_router import SubchatRouter
except Exception:
    SubchatRouter = None

try:
    from core.subchat_bridge import SubchatBridge
except Exception:
    SubchatBridge = None

try:
    from core.agent_manager import AgentManager
except Exception:
    AgentManager = None

# Top-level utilities
try:
    from agent_interaction_logger import AgentInteractionLogger
except Exception:
    AgentInteractionLogger = None

try:
    from agent_permissions import AgentPermissions
except Exception:
    AgentPermissions = None

try:
    from agent_messaging import AgentMessaging
except Exception:
    AgentMessaging = None

# Simple fallback logger if module not present
def _simple_logger(path: Optional[str] = None):
    path = path or os.path.join(os.getcwd(), "core", "subchat_integrator.log")
    def log(msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            # last-resort: print
            print(f"[{ts}] {msg}")
    return log

_log = _simple_logger()


class SubchatIntegrator:
    """
    High-level orchestrator for subchat <> agent interactions.

    Typical usage:
        integrator = SubchatIntegrator(config)
        integrator.start()
        integrator.create_subchat("Business Ops", owner="user")
        integrator.route_user_to_subchat(user_id, subchat_id, message)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        _log("Initializing SubchatIntegrator")

        # components (may be None if missing)
        self.subchat_manager = SubchatManager() if SubchatManager else None
        self.runtime = SubchatRuntime() if SubchatRuntime else None
        self.router = SubchatRouter() if SubchatRouter else None
        self.bridge = SubchatBridge() if SubchatBridge else None
        self.agent_manager = AgentManager() if AgentManager else None
        self.permissions = AgentPermissions() if AgentPermissions else None
        self.messaging = AgentMessaging() if AgentMessaging else None
        self.interaction_logger = AgentInteractionLogger() if AgentInteractionLogger else None

        # internal state
        self._running = False
        self._lock = threading.RLock()

        _log(f"Components: subchat_manager={bool(self.subchat_manager)}, "
             f"runtime={bool(self.runtime)}, router={bool(self.router)}, bridge={bool(self.bridge)}, "
             f"agent_manager={bool(self.agent_manager)}, permissions={bool(self.permissions)}, "
             f"messaging={bool(self.messaging)}, interaction_logger={bool(self.interaction_logger)}")

    # -------------------------
    # Lifecycle
    # -------------------------
    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                _log("Integrator already running.")
                return {"status": "ok", "message": "already_running"}
            _log("Starting SubchatIntegrator...")
            # Start components if they have a start method
            for comp in (self.subchat_manager, self.runtime, self.router, self.bridge, self.agent_manager):
                try:
                    if comp and hasattr(comp, "start"):
                        comp.start()
                        _log(f"Started component: {comp.__class__.__name__}")
                except Exception as e:
                    _log(f"Warning: failed to start {comp}: {e}")
            self._running = True
            return {"status": "ok"}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if not self._running:
                _log("Integrator not running.")
                return {"status": "ok", "message": "not_running"}
            _log("Stopping SubchatIntegrator...")
            for comp in (self.bridge, self.router, self.runtime, self.subchat_manager, self.agent_manager):
                try:
                    if comp and hasattr(comp, "stop"):
                        comp.stop()
                        _log(f"Stopped component: {comp.__class__.__name__}")
                except Exception as e:
                    _log(f"Warning: failed to stop {comp}: {e}")
            self._running = False
            return {"status": "ok"}

    def health(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "components": {
                "subchat_manager": bool(self.subchat_manager),
                "runtime": bool(self.runtime),
                "router": bool(self.router),
                "bridge": bool(self.bridge),
                "agent_manager": bool(self.agent_manager),
                "permissions": bool(self.permissions),
                "messaging": bool(self.messaging),
            }
        }

    # -------------------------
    # Subchat management
    # -------------------------
    def create_subchat(self, name: str, owner: str, private: bool = False, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a subchat via SubchatManager (if available). Returns metadata including subchat_id.
        """
        _log(f"create_subchat name={name} owner={owner} private={private}")
        if not self.subchat_manager:
            _log("No SubchatManager available.")
            return {"status": "error", "error": "no_subchat_manager"}
        try:
            meta = self.subchat_manager.create(name=name, owner=owner, private=private, password=password)
            _log(f"Subchat created: {meta.get('id')}")
            return {"status": "ok", "subchat": meta}
        except Exception as e:
            _log(f"Error creating subchat: {e}")
            return {"status": "error", "error": str(e)}

    def list_subchats(self) -> List[Dict[str, Any]]:
        if not self.subchat_manager:
            return []
        try:
            return self.subchat_manager.list()
        except Exception as e:
            _log(f"Error listing subchats: {e}")
            return []

    # -------------------------
    # Routing & Permissions
    # -------------------------
    def _enforce_permissions(self, actor: str, target_subchat_id: str, action: str) -> bool:
        """
        Returns True if actor is allowed to perform action on subchat.
        action: "read", "write", "create_agent_call", etc.
        """
        _log(f"Permission check: actor={actor} subchat={target_subchat_id} action={action}")
        if not self.permissions:
            _log("No AgentPermissions module available — default deny for safety.")
            return False
        try:
            return self.permissions.is_allowed(actor=actor, subchat_id=target_subchat_id, action=action)
        except Exception as e:
            _log(f"Permission check error: {e}")
            return False

    def route_user_to_subchat(self, user_id: str, subchat_id: str, message: str) -> Dict[str, Any]:
        """
        Entry point when a user posts a message into a subchat.
        Responsible for permission checks, routing to runtime/agents, and logging.
        """
        _log(f"route_user_to_subchat user={user_id} subchat={subchat_id} msg_len={len(message)}")
        if not self._enforce_permissions(user_id, subchat_id, "write"):
            _log("Permission denied for writing to subchat.")
            return {"status": "error", "error": "permission_denied"}

        # Log the incoming user message
        self._log_interaction("user->subchat", {"user": user_id, "subchat": subchat_id, "text": message})

        # Route via router/bridge to runtime
        try:
            if self.router:
                routed = self.router.route_to_runtime(subchat_id=subchat_id, content=message, user=user_id)
                _log(f"Routed via router: {routed}")
            elif self.bridge:
                routed = self.bridge.send_to_runtime(subchat_id=subchat_id, content=message, user=user_id)
                _log(f"Routed via bridge: {routed}")
            elif self.runtime:
                routed = self.runtime.handle_message(subchat_id=subchat_id, user=user_id, text=message)
                _log(f"Runtime handled message: {routed}")
            else:
                _log("No router/bridge/runtime available to handle message.")
                return {"status": "error", "error": "no_runtime"}
        except Exception as e:
            _log(f"Error routing message: {e}")
            return {"status": "error", "error": str(e)}

        # Optionally auto-invoke agents if subchat rules allow and user requested assist
        try:
            if self.subchat_manager and self.subchat_manager.should_invoke_agents(subchat_id):
                # Get allowed agents
                agents = self.subchat_manager.get_assigned_agents(subchat_id)
                for ag in agents[: self.config.get("max_agents_per_subchat", 2)]:
                    # permission check for agent invocation
                    if not self._enforce_permissions("system", subchat_id, "invoke_agent"):
                        _log(f"System not allowed to invoke agent {ag}")
                        continue
                    self._invoke_agent_via_integrator(agent_name=ag, subchat_id=subchat_id, prompt=message)
        except Exception as e:
            _log(f"Agent invocation error: {e}")

        return {"status": "ok", "routed": True}

    def _invoke_agent_via_integrator(self, agent_name: str, subchat_id: str, prompt: str) -> Dict[str, Any]:
        """
        High level helper to ask AgentManager to run an agent on behalf of a subchat.
        The integrator enforces permission checks and logs interactions.
        """
        _log(f"Invoking agent: {agent_name} for subchat {subchat_id}")
        if not self.agent_manager:
            return {"status": "error", "error": "no_agent_manager"}

        # permission: can this agent access this subchat's RAG / chunks?
        if not self._enforce_permissions(agent_name, subchat_id, "access_rag"):
            _log("Agent not permitted to access RAG for this subchat.")
            return {"status": "error", "error": "agent_permission_denied"}

        try:
            result = self.agent_manager.call_agent(agent_name, {"action": "process_prompt", "subchat_id": subchat_id, "prompt": prompt})
            # log agent response
            self._log_interaction("agent->subchat", {"agent": agent_name, "subchat": subchat_id, "result": result})
            return {"status": "ok", "result": result}
        except Exception as e:
            _log(f"Agent invocation failed: {e}")
            return {"status": "error", "error": str(e)}

    def route_agent_to_subchat(self, agent_name: str, subchat_id: str, message: str) -> Dict[str, Any]:
        """
        Called when an agent produces an output that should be posted back into a subchat.
        """
        _log(f"route_agent_to_subchat agent={agent_name} subchat={subchat_id} msg_len={len(message)}")
        # permission: can the agent write to this subchat?
        if not self._enforce_permissions(agent_name, subchat_id, "write"):
            _log("Agent denied write permission to subchat.")
            return {"status": "error", "error": "permission_denied"}

        # deliver message to runtime/bridge/router
        try:
            if self.bridge:
                self.bridge.post_to_subchat(subchat_id=subchat_id, actor=agent_name, text=message)
            elif self.router:
                self.router.post(subchat_id=subchat_id, actor=agent_name, text=message)
            elif self.runtime:
                self.runtime.inject_agent_message(subchat_id=subchat_id, agent=agent_name, text=message)
            else:
                _log("No delivery path available for agent->subchat.")
                return {"status": "error", "error": "no_delivery_path"}
        except Exception as e:
            _log(f"Error delivering agent message: {e}")
            return {"status": "error", "error": str(e)}

        # log it
        self._log_interaction("agent->subchat_post", {"agent": agent_name, "subchat": subchat_id, "text": message})
        return {"status": "ok"}

    # -------------------------
    # Logging helpers
    # -------------------------
    def _log_interaction(self, typ: str, payload: Dict[str, Any]):
        """
        Central place to record agent/subchat/user interactions.
        If an AgentInteractionLogger is present we use it; otherwise fallback to file logger.
        """
        entry = {"ts": int(time.time()), "type": typ, "payload": payload}
        try:
            if self.interaction_logger:
                self.interaction_logger.log(entry)
            else:
                # fallback: append to local json lines file
                logpath = os.path.join(os.getcwd(), "core", "agent_interactions.log")
                with open(logpath, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _log(f"Logged interaction type={typ}")
        except Exception as e:
            _log(f"Failed to log interaction: {e}")

    # -------------------------
    # Utilities
    # -------------------------
    def run_health_check(self) -> Dict[str, Any]:
        """
        Run a quick health check across components. Returns a dict summarizing health.
        """
        summary = self.health()
        # extra checks (optional)
        ok = True
        details = {}
        try:
            if self.agent_manager and hasattr(self.agent_manager, "list_agents"):
                agents = self.agent_manager.list_agents()
                details["agent_count"] = len(agents)
        except Exception as e:
            details["agent_error"] = str(e)
            ok = False

        try:
            if self.subchat_manager and hasattr(self.subchat_manager, "list"):
                details["subchat_count"] = len(self.subchat_manager.list())
        except Exception as e:
            details["subchat_error"] = str(e)
            ok = False

        summary.update({"ok": ok, "details": details})
        _log(f"Health check: ok={ok} details={details}")
        return summary

    def shutdown(self):
        _log("Integrator shutdown initiated.")
        self.stop()

# Module-level convenience instance
_integrator: Optional[SubchatIntegrator] = None


def get_integrator(config: Optional[Dict[str, Any]] = None) -> SubchatIntegrator:
    global _integrator
    if _integrator is None:
        _integrator = SubchatIntegrator(config=config)
    return _integrator


# Quick CLI test when run as a script
if __name__ == "__main__":
    integrator = get_integrator()
    print("SubchatIntegrator quick health:", integrator.run_health_check())





