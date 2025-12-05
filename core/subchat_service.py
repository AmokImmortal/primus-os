"""
/core/subchat_service.py

High-level SubChat service that ties together SubChat components:
- loader, storage, runtime, session manager, event bus, policy/enforcer, and utilities.

This file provides a single entrypoint (SubChatService) used by PRIMUS core to manage
subchat lifecycle, I/O, persistence, and guarded interactions between subchats and agents.

The service uses defensive programming and logs all important actions. It expects the
other subchat components to expose simple well-named methods (load/save/create/start/stop/etc.)
so the service remains an orchestration wrapper — not heavy implementation logic.
"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

# Relative imports to subchat components (these modules are expected to exist in /core)
try:
    from .subchat_loader import SubchatLoader
    from .subchat_storage import SubChatStorage
    from .subchat_runtime import SubChatRuntime
    from .subchat_session_manager import SubChatSessionManager
    from .subchat_event_bus import SubChatEventBus
    from .subchat_policy import SubChatPolicyManager
    from .subchat_sanitizer import SubChatSanitizer
except Exception:
    # Graceful fallbacks if some modules are missing during early development/testing.
    SubchatLoader = None
    SubChatStorage = None
    SubChatRuntime = None
    SubChatSessionManager = None
    SubChatEventBus = None
    SubChatPolicyManager = None
    SubChatSanitizer = None


LOG = logging.getLogger("primus.subchat_service")
LOG.setLevel(logging.INFO)


class SubChatService:
    """
    Orchestrates subchat components. Keeps a registry of active subchats and sessions,
    coordinates load/save, forwards inputs to runtime, and publishes events.
    """

    def __init__(self,
                 base_dir: Optional[str] = None,
                 enable_autosave: bool = True):
        self.base_dir = Path(base_dir) if base_dir else (Path(__file__).resolve().parents[1] / "sub_chats")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Components (may be None during early development; guard usage)
        self.loader = SubchatLoader(self.base_dir) if SubchatLoader else None
        self.storage = SubChatStorage(self.base_dir) if SubChatStorage else None
        self.runtime = SubChatRuntime() if SubChatRuntime else None
        self.session_mgr = SubChatSessionManager() if SubChatSessionManager else None
        self.event_bus = SubChatEventBus() if SubChatEventBus else None
        self.policy = SubChatPolicyManager() if SubChatPolicyManager else None
        self.sanitizer = SubChatSanitizer() if SubChatSanitizer else None

        # In-memory registry: id -> metadata
        self.registry: Dict[str, Dict[str, Any]] = {}

        # Autosave options
        self.enable_autosave = bool(enable_autosave)

        LOG.info("SubChatService initialized (base_dir=%s)", str(self.base_dir))

    # -----------------------------
    # Basic management
    # -----------------------------
    def list_subchats(self) -> List[Dict[str, Any]]:
        """Return a list of known subchats with minimal metadata."""
        try:
            # Prefer storage-based listing if available
            if self.storage:
                items = self.storage.list_all()
                LOG.debug("Listed %d subchats via storage.", len(items))
                return items
        except Exception as e:
            LOG.exception("Error listing subchats from storage: %s", e)

        # Fallback: return registry contents
        return [{"id": sid, **meta} for sid, meta in self.registry.items()]

    def create_subchat(self, subchat_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a subchat directory and register it. Returns metadata dict."""
        metadata = metadata or {}
        try:
            # Policy check
            if self.policy and not self.policy.allow_create(subchat_id, metadata):
                LOG.warning("Policy prevented creation of subchat '%s'.", subchat_id)
                return {"status": "error", "reason": "policy_denied"}

            if self.storage:
                self.storage.create(subchat_id, metadata)
            else:
                # Basic filesystem fallback
                sc_dir = self.base_dir / subchat_id
                sc_dir.mkdir(parents=True, exist_ok=True)
                (sc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

            self.registry[subchat_id] = {"id": subchat_id, **metadata}
            LOG.info("Created subchat '%s'.", subchat_id)

            if self.event_bus:
                self.event_bus.publish("subchat.created", {"id": subchat_id, "metadata": metadata})

            return {"status": "ok", "id": subchat_id}
        except Exception as e:
            LOG.exception("Failed to create subchat '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    def load_subchat(self, subchat_id: str) -> Dict[str, Any]:
        """Load subchat metadata + persisted state into memory."""
        try:
            if self.loader:
                metadata = self.loader.load(subchat_id)
            elif self.storage:
                metadata = self.storage.load_metadata(subchat_id)
            else:
                # fallback read metadata.json
                path = self.base_dir / subchat_id / "metadata.json"
                metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

            self.registry[subchat_id] = {"id": subchat_id, **(metadata or {})}
            LOG.info("Loaded subchat '%s'.", subchat_id)

            if self.event_bus:
                self.event_bus.publish("subchat.loaded", {"id": subchat_id, "metadata": metadata})

            return {"status": "ok", "id": subchat_id, "metadata": metadata}
        except Exception as e:
            LOG.exception("Failed to load subchat '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    def save_subchat(self, subchat_id: str) -> Dict[str, Any]:
        """Persist a subchat's state to storage."""
        try:
            if self.storage:
                self.storage.save(subchat_id)
            else:
                LOG.debug("No storage backend present; skipping save for '%s'.", subchat_id)

            if self.event_bus:
                self.event_bus.publish("subchat.saved", {"id": subchat_id})

            LOG.info("Saved subchat '%s'.", subchat_id)
            return {"status": "ok", "id": subchat_id}
        except Exception as e:
            LOG.exception("Failed to save subchat '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    def delete_subchat(self, subchat_id: str) -> Dict[str, Any]:
        """Remove subchat from disk and registry (use cautiously)."""
        try:
            if self.policy and not self.policy.allow_delete(subchat_id):
                LOG.warning("Policy prevented deletion of subchat '%s'.", subchat_id)
                return {"status": "error", "reason": "policy_denied"}

            if self.storage:
                self.storage.delete(subchat_id)
            else:
                sc_dir = self.base_dir / subchat_id
                if sc_dir.exists() and sc_dir.is_dir():
                    # simple, non-recursive removal
                    for p in sc_dir.iterdir():
                        try:
                            p.unlink()
                        except Exception:
                            pass
                    sc_dir.rmdir()

            self.registry.pop(subchat_id, None)

            if self.event_bus:
                self.event_bus.publish("subchat.deleted", {"id": subchat_id})

            LOG.info("Deleted subchat '%s'.", subchat_id)
            return {"status": "ok", "id": subchat_id}
        except Exception as e:
            LOG.exception("Failed to delete subchat '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    # -----------------------------
    # Runtime and sessions
    # -----------------------------
    def start_session(self, subchat_id: str, session_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start an interactive session for a subchat via session manager + runtime."""
        try:
            if self.session_mgr is None or self.runtime is None:
                LOG.error("Session manager or runtime not available.")
                return {"status": "error", "reason": "missing_components"}

            # Load subchat if not in registry
            if subchat_id not in self.registry:
                self.load_subchat(subchat_id)

            session = self.session_mgr.start_session(subchat_id, session_opts or {})
            self.runtime.attach_session(session)

            LOG.info("Started session %s for subchat '%s'.", session.get("id"), subchat_id)
            if self.event_bus:
                self.event_bus.publish("session.started", {"subchat": subchat_id, "session": session.get("id")})

            return {"status": "ok", "session": session}
        except Exception as e:
            LOG.exception("Failed to start session for '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    def stop_session(self, session_id: str) -> Dict[str, Any]:
        """Stop a running session cleanly."""
        try:
            if self.session_mgr is None:
                return {"status": "error", "reason": "missing_session_manager"}

            info = self.session_mgr.stop_session(session_id)
            if self.event_bus:
                self.event_bus.publish("session.stopped", {"session": session_id})

            LOG.info("Stopped session %s", session_id)
            return {"status": "ok", "info": info}
        except Exception as e:
            LOG.exception("Failed to stop session %s: %s", session_id, e)
            return {"status": "error", "reason": str(e)}

    def send_input(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """Sanitize, policy-check, and forward user input to the runtime for processing."""
        try:
            # session lookup
            if not self.session_mgr:
                return {"status": "error", "reason": "missing_session_manager"}
            session = self.session_mgr.get_session(session_id)
            if session is None:
                return {"status": "error", "reason": "session_not_found"}

            subchat_id = session.get("subchat_id")

            # policy enforcement (pre)
            if self.policy and not self.policy.allow_input(subchat_id, user_input):
                LOG.warning("Policy blocked input to subchat '%s'.", subchat_id)
                return {"status": "error", "reason": "policy_blocked"}

            # sanitize
            if self.sanitizer:
                safe_input = self.sanitizer.sanitize(user_input)
            else:
                safe_input = user_input

            # publish incoming event
            if self.event_bus:
                self.event_bus.publish("session.input", {"session": session_id, "input": safe_input})

            # runtime process
            if self.runtime:
                result = self.runtime.process(session_id, safe_input)
            else:
                result = {"status": "ok", "output": "[runtime-missing]"}

            # post-processing / policy (post)
            if self.policy:
                result = self.policy.apply_output_filters(subchat_id, result)

            # publish outgoing event
            if self.event_bus:
                self.event_bus.publish("session.output", {"session": session_id, "output": result})

            # autosave if enabled
            if self.enable_autosave and self.storage:
                try:
                    self.storage.save_session_state(session_id)
                except Exception:
                    LOG.debug("Autosave failed for session %s.", session_id)

            return {"status": "ok", "result": result}
        except Exception as e:
            LOG.exception("Error sending input to session %s: %s", session_id, e)
            return {"status": "error", "reason": str(e)}

    # -----------------------------
    # Utilities / maintenance
    # -----------------------------
    def backup_subchat(self, subchat_id: str, dest_path: Optional[str] = None) -> Dict[str, Any]:
        """Create a portable backup for a subchat (zip/json)."""
        try:
            if self.storage:
                path = self.storage.backup(subchat_id, dest_path)
            else:
                # simple metadata-only backup
                path = str(self.base_dir / f"{subchat_id}_backup.json")
                meta = self.registry.get(subchat_id, {})
                Path(path).write_text(json.dumps(meta, indent=2), encoding="utf-8")

            LOG.info("Backup created for subchat '%s' -> %s", subchat_id, path)
            return {"status": "ok", "path": str(path)}
        except Exception as e:
            LOG.exception("Failed to backup subchat '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    def restore_subchat(self, backup_path: str) -> Dict[str, Any]:
        """Restore a subchat from a backup created by backup_subchat."""
        try:
            if self.storage:
                info = self.storage.restore(backup_path)
                LOG.info("Restored subchat from %s", backup_path)
                return {"status": "ok", "info": info}
            else:
                # fallback: read metadata file name pattern
                data = json.loads(Path(backup_path).read_text(encoding="utf-8"))
                subchat_id = data.get("id") or data.get("name") or Path(backup_path).stem
                self.create_subchat(subchat_id, data)
                return {"status": "ok", "id": subchat_id}
        except Exception as e:
            LOG.exception("Restore failed from %s: %s", backup_path, e)
            return {"status": "error", "reason": str(e)}

    def enforce_policy_now(self, subchat_id: str) -> Dict[str, Any]:
        """Run immediate policy re-evaluation for the subchat (useful after config changes)."""
        try:
            if self.policy is None:
                return {"status": "error", "reason": "no_policy_manager"}

            meta = self.registry.get(subchat_id, {})
            result = self.policy.evaluate(subchat_id, meta)
            LOG.info("Policy evaluated for '%s': %s", subchat_id, result)
            return {"status": "ok", "result": result}
        except Exception as e:
            LOG.exception("Policy enforcement error for '%s': %s", subchat_id, e)
            return {"status": "error", "reason": str(e)}

    # -----------------------------
    # Shutdown
    # -----------------------------
    def shutdown(self):
        """Attempt a graceful shutdown of runtime and session manager."""
        try:
            if self.session_mgr:
                self.session_mgr.stop_all()
            if self.runtime:
                self.runtime.shutdown()
            if self.event_bus:
                self.event_bus.publish("service.shutdown", {"service": "subchat"})
            LOG.info("SubChatService shutdown complete.")
        except Exception as e:
            LOG.exception("Error during SubChatService shutdown: %s", e)