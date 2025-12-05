# primus_bridge.py
"""
PRIMUS Bridge — Unified internal entrypoint for agent calls and external connectors.

Purpose:
- Provide a single, well-structured API for:
  * Agent -> Agent calls (via Dispatcher)
  * Agent -> External connector calls (email, web, model APIs, etc)
  * Core health/status checks
- Enforce simple permission checks and logging
- Return deterministic JSON-like dict responses

Usage:
    from primus_bridge import PrimusBridge
    bridge = PrimusBridge()
    resp = bridge.handle_request({
        "type": "agent_call",
        "agent": "FileAgent",
        "payload": {"action": "ping"}
    })
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Attempt to import the dispatcher bridge (our internal agent dispatcher)
try:
    from intelligence.dispatcher.bridge import Bridge as DispatcherBridge  # type: ignore
except Exception:
    DispatcherBridge = None  # We'll handle fallback at runtime

ROOT = Path(__file__).resolve().parents[1]  # points to System/ by default
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "primus_bridge.log"

# Permissions/config path (optional)
PERMISSIONS_PATH = ROOT / "configs" / "bridge_permissions.json"

# Configure logger
_logger = logging.getLogger("primus_bridge")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    _logger.addHandler(fh)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class PermissionManager:
    """
    Lightweight permission manager that reads an optional JSON config:
    {
      "global": {"allow_external": false},
      "agents": {
         "FileAgent": {"allow_external": false, "allowed_connectors": ["email", "websearch"]},
         "MarketingAgent": {"allow_external": true, "allowed_connectors": ["openai", "image_api"]}
      }
    }

    If config missing: permissive for local agent_call, restrictive for external connector calls.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or PERMISSIONS_PATH
        self.cfg: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.cfg = json.load(f)
                    _logger.debug("Loaded permissions from %s", str(self.path))
            except Exception as e:
                _logger.exception("Failed to load permissions file: %s", e)
                self.cfg = {}
        else:
            # sensible defaults
            self.cfg = {
                "global": {"allow_external": False},
                "agents": {}
            }

    def allows_connector(self, agent: str, connector: str) -> bool:
        # Global switch
        if not self.cfg.get("global", {}).get("allow_external", False):
            # still allow if agent explicitly allows
            agent_cfg = self.cfg.get("agents", {}).get(agent, {})
            return bool(agent_cfg.get("allow_external", False) and connector in agent_cfg.get("allowed_connectors", []))
        # If global allows, still check per-agent allow list (if present)
        agent_cfg = self.cfg.get("agents", {}).get(agent)
        if agent_cfg is None:
            return True
        # If agent config exists, check connector list and allow_external flag
        if agent_cfg.get("allow_external", True):
            allowed = agent_cfg.get("allowed_connectors")
            if allowed is None:
                return True
            return connector in allowed
        return False

    def allows_agent_to_agent(self, source: str, target: str) -> bool:
        # Simple rule: allow by default unless explicitly blocked
        agent_cfg = self.cfg.get("agents", {}).get(source, {})
        blocked = agent_cfg.get("blocked_agents", [])
        return target not in blocked


class PrimusBridge:
    """
    Central bridge used by PRIMUS master / core and by agents when they want to call
    other agents or external connectors. All calls go through handle_request().

    Supported request shapes (dictionary form):
      - Health check:
            {"type": "health"}
      - Agent call:
            {"type": "agent_call", "agent": "<AgentName>", "payload": {"action": "...", ...}, "caller": "<AgentName/PRIMUS>"}
      - Connector call:
            {"type": "connector_call", "connector": "<name>", "action": "<op>", "payload": {...}, "caller": "<AgentName/PRIMUS>"}
      - List connectors:
            {"type": "list_connectors"}
      - Raw dispatch (internal):
            {"type": "raw_dispatch", "task": { ... }}  # forwarded to dispatcher.dispatch()
    """

    def __init__(self):
        self.pm = PermissionManager()
        # instantiate dispatcher bridge if available
        self.dispatcher = None
        if DispatcherBridge is not None:
            try:
                self.dispatcher = DispatcherBridge()
            except Exception as e:
                _logger.exception("Failed to instantiate DispatcherBridge: %s", e)
                self.dispatcher = None
        _logger.info("PrimusBridge initialized. Dispatcher available: %s", bool(self.dispatcher))

    # -------------------------
    # Helpers
    # -------------------------
    def _log_request(self, req: Dict[str, Any], result: Dict[str, Any]):
        try:
            _logger.info("REQ type=%s caller=%s target=%s result=%s",
                         req.get("type"),
                         req.get("caller"),
                         req.get("agent") or req.get("connector") or req.get("task"),
                         result.get("status"))
        except Exception:
            _logger.exception("Failed to write structured request log.")
        # Also write full debug
        _logger.debug("Request payload: %s", json.dumps(req, default=str, ensure_ascii=False))
        _logger.debug("Result payload: %s", json.dumps(result, default=str, ensure_ascii=False))

    def _safe_import_connector(self, name: str):
        """
        Dynamic import for connector modules under package 'api.<name>'
        Connector module must provide a callable `handle(action:str, payload:dict, caller:str)` -> dict
        OR provide a class Connector with method handle(action,payload,caller).
        """
        module_path_variants = [f"api.{name}", name]
        mod = None
        last_err = None
        for path in module_path_variants:
            try:
                mod = importlib.import_module(path)
                break
            except Exception as e:
                last_err = e
                continue
        if mod is None:
            raise ImportError(f"Connector '{name}' not found ({last_err})")
        # find handler
        if hasattr(mod, "handle") and callable(getattr(mod, "handle")):
            return getattr(mod, "handle")
        # check for class
        if hasattr(mod, "Connector"):
            ctor = getattr(mod, "Connector")
            inst = ctor()
            if hasattr(inst, "handle") and callable(getattr(inst, "handle")):
                return inst.handle
        # fallback: not usable
        raise ImportError(f"Connector '{name}' does not expose a usable handle()")

    # -------------------------
    # Public API
    # -------------------------
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entrypoint. Validates request, enforces permissions, routes to the appropriate backend.
        Always returns a dict with at least a 'status' field ("ok" or "error") and an optional 'result'.
        """
        req = dict(request)  # copy to avoid mutation
        req_type = req.get("type", "").lower()
        caller = req.get("caller", "PRIMUS")
        try:
            if req_type in ("health", ""):
                res = {"status": "ok", "time": _now(), "dispatcher": bool(self.dispatcher)}
                self._log_request(req, res)
                return res

            if req_type == "list_connectors":
                # discover connectors by trying to import modules in api package (if exists)
                connectors = []
                try:
                    api_pkg = importlib.import_module("api")
                    package_dir = Path(api_pkg.__file__).resolve().parent
                    for f in package_dir.iterdir():
                        if f.is_file() and f.suffix == ".py" and f.stem != "__init__":
                            connectors.append(f.stem)
                except Exception:
                    # fallback: attempt to look for top-level modules named in config folder
                    connectors = []
                res = {"status": "ok", "connectors": connectors}
                self._log_request(req, res)
                return res

            if req_type == "agent_call":
                agent = req.get("agent")
                payload = req.get("payload", {})
                target = agent or payload.get("agent")
                if not target:
                    res = {"status": "error", "error": "Missing 'agent' field"}
                    self._log_request(req, res)
                    return res

                # Agent-to-agent permission check (if caller provided)
                if caller and caller != "PRIMUS":
                    if not self.pm.allows_agent_to_agent(caller, target):
                        res = {"status": "error", "error": "Agent->Agent communication disallowed by policy"}
                        self._log_request(req, res)
                        return res

                # Build task expected by dispatcher
                task = {"agent": target}
                # Merge payload into task (action, params etc.)
                if isinstance(payload, dict):
                    task.update(payload)
                else:
                    # support legacy: payload might be an action string
                    task["action"] = payload

                if not self.dispatcher:
                    res = {"status": "error", "error": "Dispatcher unavailable"}
                    self._log_request(req, res)
                    return res

                try:
                    result = self.dispatcher.dispatch(task)
                    res = {"status": "ok", "result": result}
                    self._log_request(req, res)
                    return res
                except Exception as e:
                    _logger.exception("Agent dispatch error")
                    res = {"status": "error", "error": f"Agent dispatch failed: {e}"}
                    self._log_request(req, res)
                    return res

            if req_type == "raw_dispatch":
                # Advanced: forward raw task object directly to dispatcher
                task = req.get("task")
                if not task or not isinstance(task, dict):
                    res = {"status": "error", "error": "Missing/invalid 'task' field"}
                    self._log_request(req, res)
                    return res
                if not self.dispatcher:
                    res = {"status": "error", "error": "Dispatcher unavailable"}
                    self._log_request(req, res)
                    return res
                try:
                    r = self.dispatcher.dispatch(task)
                    res = {"status": "ok", "result": r}
                    self._log_request(req, res)
                    return res
                except Exception as e:
                    _logger.exception("Raw dispatch error")
                    res = {"status": "error", "error": f"Raw dispatch failed: {e}"}
                    self._log_request(req, res)
                    return res

            if req_type == "connector_call":
                connector = req.get("connector")
                action = req.get("action")
                payload = req.get("payload", {})

                if not connector:
                    res = {"status": "error", "error": "Missing 'connector' field"}
                    self._log_request(req, res)
                    return res

                # Permission check
                if not self.pm.allows_connector(caller, connector):
                    res = {"status": "error", "error": "Connector use disallowed by policy"}
                    self._log_request(req, res)
                    return res

                # Import connector handler
                try:
                    handler = self._safe_import_connector(connector)
                except Exception as e:
                    _logger.exception("Connector import error")
                    res = {"status": "error", "error": f"Connector import failed: {e}"}
                    self._log_request(req, res)
                    return res

                # Call connector handler(action, payload, caller) or handler(payload) depending on signature
                try:
                    # Try the common signature first
                    try:
                        result = handler(action, payload, caller)
                    except TypeError:
                        # fallback: handler(payload) or handler(action, payload)
                        try:
                            result = handler(payload)
                        except TypeError:
                            result = handler(action, payload)
                    # Ensure result is dict-like
                    if not isinstance(result, dict):
                        result = {"status": "ok", "result": result}
                    res = {"status": "ok", "result": result}
                    self._log_request(req, res)
                    return res
                except Exception as e:
                    _logger.exception("Connector execution error")
                    res = {"status": "error", "error": f"Connector execution failed: {e}"}
                    self._log_request(req, res)
                    return res

            # Unknown type
            res = {"status": "error", "error": f"Unknown request type: {req_type}"}
            self._log_request(req, res)
            return res

        except Exception as outer:
            _logger.exception("Unhandled bridge error")
            res = {"status": "error", "error": f"Unhandled bridge error: {outer}"}
            self._log_request(req, res)
            return res


# -------------------------
# Convenience / test
# -------------------------
def test_bridge_local_ping():
    b = PrimusBridge()
    # Try a simple agent ping (non-failing if dispatcher missing)
    r = b.handle_request({
        "type": "agent_call",
        "agent": "FileAgent",
        "payload": {"action": "ping"},
        "caller": "PRIMUS"
    })
    return r


if __name__ == "__main__":
    print("[primus_bridge] Self-test:", _now())
    br = PrimusBridge()
    print("Dispatcher available:", bool(br.dispatcher))
    print("Permissions loaded:", br.pm.cfg)
    print("Ping FileAgent:", test_bridge_local_ping())