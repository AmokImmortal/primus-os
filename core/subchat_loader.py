"""
core/subchat_loader.py

Bridge between persistent subchat storage and runtime state.
Keeps everything local-only and works with security + recovery helpers.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.subchat_security import SubchatSecurity
from core.subchat_state import SubchatStateManager


class _DefaultStorage:
    """Minimal filesystem storage for subchat payloads."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1] / "sub_chats"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> List[str]:
        return [p.name for p in self.base_dir.iterdir() if p.is_dir()]

    def create(self, subchat_id: str, metadata: Dict[str, Any]) -> None:
        sc_dir = self.base_dir / subchat_id
        sc_dir.mkdir(parents=True, exist_ok=True)
        (sc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (sc_dir / "data.json").write_text(json.dumps({"id": subchat_id, "messages": []}, indent=2), encoding="utf-8")

    def load(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        sc_dir = self.base_dir / subchat_id
        data_path = sc_dir / "data.json"
        meta_path = sc_dir / "metadata.json"
        if not sc_dir.exists():
            return None
        payload: Dict[str, Any] = {"id": subchat_id}
        if meta_path.exists():
            payload["metadata"] = json.loads(meta_path.read_text(encoding="utf-8"))
        if data_path.exists():
            payload.update(json.loads(data_path.read_text(encoding="utf-8")))
        return payload

    def delete(self, subchat_id: str) -> None:
        sc_dir = self.base_dir / subchat_id
        if sc_dir.exists():
            for item in sc_dir.iterdir():
                item.unlink(missing_ok=True)
            sc_dir.rmdir()


class SubchatRecoveryManager:
    """Store and load recovery snapshots for subchats."""

    def __init__(self, recovery_root: Optional[Path] = None):
        self.recovery_root = Path(recovery_root) if recovery_root else Path(__file__).resolve().parents[1] / "subchat_recovery"
        self.recovery_root.mkdir(parents=True, exist_ok=True)

    def get_recovery_file(self, subchat_id: str) -> Path:
        return self.recovery_root / f"{subchat_id}_recovery.json"

    def save_recovery_state(self, subchat_id: str, state_dict: Dict[str, Any]) -> None:
        path = self.get_recovery_file(subchat_id)
        path.write_text(json.dumps(state_dict, indent=2), encoding="utf-8")

    def load_recovery_state(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        path = self.get_recovery_file(subchat_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def attempt_recovery(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        return self.load_recovery_state(subchat_id)

    def delete_recovery_state(self, subchat_id: str) -> None:
        path = self.get_recovery_file(subchat_id)
        if path.exists():
            path.unlink()


class SubchatLoader:
    def __init__(
        self,
        storage: Optional[Any] = None,
        security: Optional[SubchatSecurity] = None,
        state_manager: Optional[SubchatStateManager] = None,
        recovery: Optional[SubchatRecoveryManager] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.storage = storage if storage is not None else _DefaultStorage()
        self.security = security if security is not None else SubchatSecurity()
        self.state_manager = state_manager if state_manager is not None else SubchatStateManager()
        self.recovery = recovery if recovery is not None else SubchatRecoveryManager()
        self.logger = logger

    def _log(self, msg: str):
        if self.logger:
            try:
                self.logger(msg)
            except Exception:
                pass

    def list_ids(self) -> List[str]:
        ids = set(self.storage.list_ids()) if hasattr(self.storage, "list_ids") else set()
        ids.update(self.security.list_subchats())
        return sorted(ids)

    def load_subchat(self, subchat_id: str, requester: Optional[str] = None) -> Dict[str, Any]:
        meta = self.security.get_subchat_info(subchat_id)
        if requester and not self.security.can_read(subchat_id, requester):
            raise PermissionError("Requester not allowed to read subchat")

        # Prefer recovery snapshot
        recovered = self.recovery.attempt_recovery(subchat_id) if self.recovery else None
        if recovered:
            self._log(f"Recovered subchat {subchat_id} from recovery snapshot")
            payload = {"id": subchat_id, "metadata": meta or {}, "data": recovered}
            return payload

        loaded = None
        if hasattr(self.storage, "load"):
            loaded = self.storage.load(subchat_id)
        if loaded is None:
            raise FileNotFoundError(f"Subchat {subchat_id} not found")

        payload = {"id": subchat_id, "metadata": meta or {}, "data": loaded}
        self._log(f"Loaded subchat {subchat_id}")
        return payload

    def create_subchat(
        self,
        owner: str,
        label: str,
        is_private: bool = False,
        allowed_agents: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        subchat_id = str(uuid.uuid4())
        allowed_agents = allowed_agents or []
        metadata = metadata or {}
        self.security.create_or_update_subchat(
            subchat_id=subchat_id,
            owner=owner,
            label=label,
            is_private=is_private,
            allowed_agents=allowed_agents,
            flags=metadata.get("flags", {}),
        )
        if hasattr(self.storage, "create"):
            self.storage.create(subchat_id, {"owner": owner, "label": label, **metadata})
        self.hydrate_state(subchat_id)
        self._log(f"Created subchat {subchat_id}")
        return subchat_id

    def delete_subchat(self, subchat_id: str, hard_delete: bool = False) -> None:
        if hard_delete and hasattr(self.storage, "delete"):
            self.storage.delete(subchat_id)
        else:
            self.security.update_flags(subchat_id, {"archived": True})
        if self.recovery:
            self.recovery.delete_recovery_state(subchat_id)
        if self.state_manager:
            self.state_manager.destroy(subchat_id)
        self._log(f"Deleted subchat {subchat_id} (hard_delete={hard_delete})")

    def hydrate_state(self, subchat_id: str, sandbox_mode: bool = False):
        existing = self.state_manager.get(subchat_id)
        if existing:
            return existing
        return self.state_manager.create(subchat_id, sandbox_mode=sandbox_mode)


__all__ = ["SubchatLoader", "SubchatRecoveryManager"]
