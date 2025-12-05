# /core/subchat_orchestrator.py
"""
Subchat Orchestrator for PRIMUS
-------------------------------
Coordinates all subchat subsystems (manager, runtime, router, integrator, policy, security).
Provides a single high-level API for creating, starting, stopping, routing messages to subchats,
enforcing policies/security, persisting subchat state, and querying status.

Design goals:
- Defensive: will work even if some submodules are missing (falls back to in-memory behavior).
- Simple sync API so it can be used from CLI/UI without async plumbing. Can be adapted to async later.
- Persist minimal runtime state to disk (core/subchat_state.json).
"""

from __future__ import annotations
import importlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]  # .../System
CORE_DIR = ROOT / "core"
STATE_PATH = CORE_DIR / "subchat_state.json"

# Try to import optional sub-modules. If absent, we keep None and fallback to internal logic.
def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

_subchat_manager = _try_import("core.subchat_manager")
_subchat_runtime = _try_import("core.subchat_runtime")
_subchat_router = _try_import("core.subchat_router")
_subchat_policy = _try_import("core.subchat_policy")
_subchat_security = _try_import("core.subchat_security")
_subchat_integrator = _try_import("core.subchat_integrator")


class SubchatOrchestrator:
    def __init__(self):
        self._lock = threading.RLock()
        # registry: id -> metadata/state
        self.registry: Dict[str, Dict[str, Any]] = {}
        # in-memory message logs for quick inspection (kept small)
        self.message_log: List[Dict[str, Any]] = []
        # load persisted state if available
        self._load_state()

    # -----------------------
    # Persistence
    # -----------------------
    def _load_state(self):
        try:
            if STATE_PATH.exists():
                with open(STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # basic validation
                if isinstance(data, dict):
                    self.registry = data.get("registry", {})
                    self.message_log = data.get("message_log", [])[-1000:]
        except Exception:
            # if anything fails, start with empty state
            self.registry = {}
            self.message_log = []

    def _save_state(self):
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {"registry": self.registry, "message_log": self.message_log[-1000:]}
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # -----------------------
    # Lifecycle operations
    # -----------------------
    def create_subchat(self, subchat_id: str, owner: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new subchat entry. This does not start runtime.
        """
        with self._lock:
            if subchat_id in self.registry:
                return {"status": "error", "error": "exists"}
            cfg = config.copy() if isinstance(config, dict) else {}
            self.registry[subchat_id] = {
                "id": subchat_id,
                "owner": owner,
                "config": cfg,
                "state": "created",
                "created_at": __import__("time").time(),
                "last_active": None,
            }
            self._save_state()
            return {"status": "ok", "id": subchat_id}

    def start_subchat(self, subchat_id: str) -> Dict[str, Any]:
        """
        Start runtime for a subchat. Attempts to use core.subchat_runtime if available.
        """
        with self._lock:
            meta = self.registry.get(subchat_id)
            if not meta:
                return {"status": "error", "error": "not_found"}

            if meta.get("state") in ("running", "starting"):
                return {"status": "ok", "state": meta.get("state")}

            meta["state"] = "starting"
            self._save_state()

        # Attempt to start via runtime module
        try:
            if _subchat_runtime and hasattr(_subchat_runtime, "start_subchat"):
                res = _subchat_runtime.start_subchat(subchat_id, meta)
                with self._lock:
                    meta["state"] = "running" if res.get("status") == "ok" else "error"
                    meta["last_active"] = __import__("time").time()
                    self._save_state()
                return {"status": "ok", "detail": res}
        except Exception:
            pass

        # Fallback: mark running (no-op runtime)
        with self._lock:
            meta["state"] = "running"
            meta["last_active"] = __import__("time").time()
            self._save_state()
        return {"status": "ok", "detail": "runtime_fallback"}

    def stop_subchat(self, subchat_id: str) -> Dict[str, Any]:
        with self._lock:
            meta = self.registry.get(subchat_id)
            if not meta:
                return {"status": "error", "error": "not_found"}
            meta["state"] = "stopping"
            self._save_state()

        try:
            if _subchat_runtime and hasattr(_subchat_runtime, "stop_subchat"):
                res = _subchat_runtime.stop_subchat(subchat_id)
                with self._lock:
                    meta["state"] = "stopped" if res.get("status") == "ok" else "error"
                    self._save_state()
                return {"status": "ok", "detail": res}
        except Exception:
            pass

        with self._lock:
            meta["state"] = "stopped"
            self._save_state()
        return {"status": "ok", "detail": "stopped_fallback"}

    def remove_subchat(self, subchat_id: str) -> Dict[str, Any]:
        with self._lock:
            if subchat_id not in self.registry:
                return {"status": "error", "error": "not_found"}
            # stop if running
            if self.registry[subchat_id].get("state") == "running":
                try:
                    self.stop_subchat(subchat_id)
                except Exception:
                    pass
            del self.registry[subchat_id]
            self._save_state()
            return {"status": "ok"}

    def list_subchats(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.registry.values())

    # -----------------------
    # Messaging / routing
    # -----------------------
    def route_message(self, from_id: str, to_id: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Route a message from one subchat to another (or to PRIMUS).
        Enforces policy/security via optional modules; logs the interaction to subchat message_log.
        """
        entry = {
            "from": from_id,
            "to": to_id,
            "message": message,
            "metadata": metadata or {},
            "timestamp": __import__("time").time(),
        }

        # Security check
        if _subchat_security and hasattr(_subchat_security, "authorize_message"):
            try:
                allowed = _subchat_security.authorize_message(from_id, to_id, message, entry["metadata"])
                if not allowed:
                    entry["rejected_by_security"] = True
                    self._append_log(entry)
                    return {"status": "error", "error": "unauthorized"}
            except Exception:
                # on failure, be conservative and block
                entry["rejected_by_security"] = True
                self._append_log(entry)
                return {"status": "error", "error": "security_module_error"}

        # Policy check
        if _subchat_policy and hasattr(_subchat_policy, "apply_policy"):
            try:
                policy_ok = _subchat_policy.apply_policy(from_id, to_id, message, entry["metadata"])
                if not policy_ok:
                    entry["rejected_by_policy"] = True
                    self._append_log(entry)
                    return {"status": "error", "error": "policy_block"}
            except Exception:
                entry["rejected_by_policy"] = True
                self._append_log(entry)
                return {"status": "error", "error": "policy_module_error"}

        # Route via router/integrator if available
        try:
            if _subchat_router and hasattr(_subchat_router, "route"):
                routed = _subchat_router.route(from_id, to_id, message, entry["metadata"])
                entry["routed_via"] = "router"
                self._append_log(entry)
                return {"status": "ok", "detail": routed}
        except Exception:
            pass

        # Fallback: deliver to runtime handler if present
        try:
            if _subchat_runtime and hasattr(_subchat_runtime, "deliver_message"):
                delivered = _subchat_runtime.deliver_message(to_id, from_id, message, entry["metadata"])
                entry["delivered"] = True
                self._append_log(entry)
                return {"status": "ok", "detail": delivered}
        except Exception:
            pass

        # Final fallback: record and return success (no real delivery)
        entry["delivered"] = False
        self._append_log(entry)
        return {"status": "ok", "detail": "logged_only"}

    def broadcast(self, from_id: str, message: str, target_filter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Broadcast message to multiple subchats matching the target_filter (e.g., owner, state).
        """
        with self._lock:
            targets = []
            for sid, meta in self.registry.items():
                ok = True
                if target_filter:
                    for k, v in target_filter.items():
                        if meta.get(k) != v:
                            ok = False
                            break
                if ok:
                    targets.append(sid)

        results = {}
        for t in targets:
            results[t] = self.route_message(from_id, t, message)
        return {"status": "ok", "results": results}

    def _append_log(self, entry: Dict[str, Any]):
        with self._lock:
            self.message_log.append(entry)
            # keep last 1000 messages
            if len(self.message_log) > 1000:
                self.message_log = self.message_log[-1000:]
            # update last_active for destination
            to_id = entry.get("to")
            if to_id and to_id in self.registry:
                self.registry[to_id]["last_active"] = entry["timestamp"]
            self._save_state()

    def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.message_log[-limit:])

    # -----------------------
    # Policy & Security helpers
    # -----------------------
    def set_policy(self, subchat_id: str, policy_blob: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            meta = self.registry.get(subchat_id)
            if not meta:
                return {"status": "error", "error": "not_found"}
            meta.setdefault("config", {})["policy"] = policy_blob
            self._save_state()
            # if module exists, notify it
            try:
                if _subchat_policy and hasattr(_subchat_policy, "update_policy"):
                    _subchat_policy.update_policy(subchat_id, policy_blob)
            except Exception:
                pass
            return {"status": "ok"}

    def enforce_security_rule(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        # Best-effort push to security module
        try:
            if _subchat_security and hasattr(_subchat_security, "add_rule"):
                _subchat_security.add_rule(rule)
                return {"status": "ok"}
        except Exception:
            pass
        return {"status": "error", "error": "security_module_unavailable"}

    # -----------------------
    # Utilities
    # -----------------------
    def get_subchat_state(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.registry.get(subchat_id)

    def attach_metadata(self, subchat_id: str, key: str, value: Any) -> Dict[str, Any]:
        with self._lock:
            meta = self.registry.get(subchat_id)
            if not meta:
                return {"status": "error", "error": "not_found"}
            meta.setdefault("config", {})[key] = value
            self._save_state()
            return {"status": "ok"}

    # -----------------------
    # Diagnostic helpers
    # -----------------------
    def health_check(self) -> Dict[str, Any]:
        """
        Return health info about orchestrator and which optional modules are loaded.
        """
        modules = {
            "subchat_manager": bool(_subchat_manager),
            "subchat_runtime": bool(_subchat_runtime),
            "subchat_router": bool(_subchat_router),
            "subchat_policy": bool(_subchat_policy),
            "subchat_security": bool(_subchat_security),
            "subchat_integrator": bool(_subchat_integrator),
        }
        with self._lock:
            return {
                "status": "ok",
                "modules": modules,
                "subchat_count": len(self.registry),
            }


# Singleton instance for ease of use when imported
_orchestrator_singleton: Optional[SubchatOrchestrator] = None


def get_orchestrator() -> SubchatOrchestrator:
    global _orchestrator_singleton
    if _orchestrator_singleton is None:
        _orchestrator_singleton = SubchatOrchestrator()
    return _orchestrator_singleton


# Quick CLI test when executed directly
if __name__ == "__main__":
    orch = get_orchestrator()
    print("Subchat Orchestrator Health:", orch.health_check())