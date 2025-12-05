"""
SubChat Personality Inheritance Engine
Location: C:\P.R.I.M.U.S OS\System\core\subchat_personality.py

Responsibilities:
- Manage personality inheritance from parent (PRIMUS or agent) to sub-chats
- Allow controlled overrides, growth, and restrictions per-subchat
- Support approval workflow for personality changes (propose -> approve)
- Persist personalities to disk (JSON) under core/subchat_personalities.json
- Enforce hard limits so subchats cannot modify protected/core traits
- Provide utility functions to inspect, export, and import personalities

Design notes:
- Data is intentionally JSON-first for portability. Later DB replacement is easy.
- This module is synchronous and light-weight (no external locking libs).
- The manager enforces the rule: subchats inherit from parent but do NOT change parent.
"""

from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from copy import deepcopy
import datetime
import uuid

ROOT = Path(__file__).resolve().parents[1]  # .../core -> System/core -> parents[1] = System
STORE_PATH = ROOT / "subchat_personalities.json"

# Defaults / hard constraints
DEFAULT_PERSONALITY_TEMPLATE = {
    "name": "unnamed",
    "description": "",
    "tone": "neutral",          # e.g., neutral, friendly, professional, curt
    "verbosity": "balanced",    # terse | balanced | verbose
    "permissions": {},          # per-feature permission overrides
    "safety": {},               # safety & content guard settings
    "growth": {                 # growth metadata: how aggressive subchat may evolve
        "level": 0,             # 0 = no growth, higher = more allowed changes
        "max_level": 5,
        "auto_growth": False
    },
    "metadata": {},
}

# Traits that are protected and cannot be altered by subchats (even via propose)
PROTECTED_TRAITS = {
    "core_integrity", "bootstrap_keys", "root_access", "system_paths", "agent_registry"
}

# Minimal schema keys allowed for personality entries (helps validate)
ALLOWED_TOP_LEVEL_KEYS = set(DEFAULT_PERSONALITY_TEMPLATE.keys()) | {"parent", "created_at", "updated_at", "pending_updates", "id"}


def _atomic_write(path: Path, content: str):
    """
    Write file atomically to reduce corruption risk.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        shutil.move(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


class SubchatPersonalityManager:
    """
    Manager for subchat personalities.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self._db: Dict[str, Dict[str, Any]] = {}
        self._load_db()

    # ---------- Persistence ----------
    def _load_db(self):
        if self.store_path.exists():
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._db = data
                else:
                    self._db = {}
            except Exception:
                # proceed with empty db to avoid crash
                self._db = {}
        else:
            # ensure parent dir exists
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = {}
            self._save_db()

    def _save_db(self):
        try:
            content = json.dumps(self._db, indent=2, ensure_ascii=False)
            _atomic_write(self.store_path, content)
        except Exception as e:
            # best-effort: print; caller should log appropriately
            print("[subchat_personality] Failed to save DB:", e)

    # ---------- Utilities ----------
    def _now(self) -> str:
        return datetime.datetime.utcnow().isoformat() + "Z"

    def list_subchats(self) -> List[str]:
        return list(self._db.keys())

    def get(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        return deepcopy(self._db.get(subchat_id))

    # ---------- Creation & Inheritance ----------
    def create_subchat(
        self,
        parent_id: str,
        subchat_id: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
        restrictions: Optional[Dict[str, Any]] = None,
        require_approval: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a subchat personality derived from parent (parent must exist in DB).
        If parent_id is not found, parent defaults to a minimal template.
        """
        subchat_id = subchat_id or str(uuid.uuid4())
        parent = deepcopy(self._db.get(parent_id, {}))
        if not parent:
            # Parent missing: start from template (this can be PRIMUS base)
            parent_personality = deepcopy(DEFAULT_PERSONALITY_TEMPLATE)
            parent_personality["name"] = f"derived_from_{parent_id}"
        else:
            parent_personality = deepcopy(parent.get("personality", DEFAULT_PERSONALITY_TEMPLATE))

        # Start derived personality (do not change parent)
        derived = deepcopy(parent_personality)
        # Apply overrides (but do not allow protected traits)
        if overrides:
            clean_overrides = self._filter_protected_traits(overrides)
            self._deep_update(derived, clean_overrides)

        # Apply restrictions (stored separately)
        restrictions = restrictions or {}

        entry = {
            "id": subchat_id,
            "parent": parent_id,
            "personality": derived,
            "restrictions": restrictions,
            "created_at": self._now(),
            "updated_at": self._now(),
            "pending_updates": [],  # list of proposed updates awaiting approval
        }

        # initial growth metadata: inherit parent's growth but clamp to allowed max
        entry["personality"].setdefault("growth", deepcopy(DEFAULT_PERSONALITY_TEMPLATE["growth"]))
        # If parent has growth, inherit but do not exceed parent.max_level
        if parent:
            parent_growth = parent.get("personality", {}).get("growth", {})
            if parent_growth:
                entry["personality"]["growth"]["level"] = min(
                    entry["personality"]["growth"].get("level", 0),
                    parent_growth.get("max_level", entry["personality"]["growth"]["max_level"])
                )

        self._db[subchat_id] = entry
        self._save_db()
        return deepcopy(entry)

    # ---------- Propose / Approve workflow ----------
    def propose_update(self, subchat_id: str, proposer: str, changes: Dict[str, Any], reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a proposed personality update to pending_updates. Does not apply changes.
        Returns the created proposal metadata.
        """
        if subchat_id not in self._db:
            return {"status": "error", "error": "subchat_not_found"}

        clean_changes = self._filter_protected_traits(changes)
        proposal = {
            "proposal_id": str(uuid.uuid4()),
            "proposer": proposer,
            "changes": clean_changes,
            "reason": reason or "",
            "created_at": self._now(),
            "status": "pending"
        }
        self._db[subchat_id].setdefault("pending_updates", []).append(proposal)
        self._db[subchat_id]["updated_at"] = self._now()
        self._save_db()
        return {"status": "ok", "proposal": proposal}

    def list_proposals(self, subchat_id: str) -> List[Dict[str, Any]]:
        if subchat_id not in self._db:
            return []
        return deepcopy(self._db[subchat_id].get("pending_updates", []))

    def approve_proposal(self, subchat_id: str, proposal_id: str, approver: str) -> Dict[str, Any]:
        """
        Approve and apply a pending proposal. Returns status.
        """
        entry = self._db.get(subchat_id)
        if not entry:
            return {"status": "error", "error": "subchat_not_found"}

        for p in entry.get("pending_updates", []):
            if p["proposal_id"] == proposal_id and p["status"] == "pending":
                # Apply changes
                try:
                    self._deep_update(entry["personality"], p["changes"])
                    p["status"] = "approved"
                    p["approved_by"] = approver
                    p["approved_at"] = self._now()
                    entry["updated_at"] = self._now()
                    self._save_db()
                    return {"status": "ok", "applied": p}
                except Exception as e:
                    return {"status": "error", "error": f"apply_failed: {e}"}

        return {"status": "error", "error": "proposal_not_found_or_not_pending"}

    def reject_proposal(self, subchat_id: str, proposal_id: str, approver: str, reason: Optional[str] = None) -> Dict[str, Any]:
        entry = self._db.get(subchat_id)
        if not entry:
            return {"status": "error", "error": "subchat_not_found"}

        for p in entry.get("pending_updates", []):
            if p["proposal_id"] == proposal_id and p["status"] == "pending":
                p["status"] = "rejected"
                p["rejected_by"] = approver
                p["rejected_at"] = self._now()
                p["rejection_reason"] = reason or ""
                entry["updated_at"] = self._now()
                self._save_db()
                return {"status": "ok", "rejected": p}

        return {"status": "error", "error": "proposal_not_found_or_not_pending"}

    # ---------- Merge / Update Helpers ----------
    def _deep_update(self, base: Dict[str, Any], updates: Dict[str, Any]):
        """
        Recursive update: merges nested dicts rather than replace.
        """
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _filter_protected_traits(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove protected traits from change dict. Works recursively.
        """
        if not isinstance(changes, dict):
            return changes
        filtered = {}
        for k, v in changes.items():
            if k in PROTECTED_TRAITS:
                # ignore protected trait change
                continue
            # If nested dict: filter recursively
            if isinstance(v, dict):
                filtered[k] = self._filter_protected_traits(v)
            else:
                filtered[k] = v
        return filtered

    # ---------- Enforcement ----------
    def enforce_constraints(self, subchat_id: str) -> List[str]:
        """
        Validate and enforce constraints on a given subchat personality.
        Returns list of warnings/fixes applied.
        """
        warnings = []
        entry = self._db.get(subchat_id)
        if not entry:
            return ["subchat_not_found"]

        p = entry.get("personality", {})

        # Ensure allowed top-level keys
        for key in list(p.keys()):
            if key not in ALLOWED_TOP_LEVEL_KEYS:
                warnings.append(f"removed_unknown_key:{key}")
                p.pop(key, None)

        # Growth level clamp
        growth = p.setdefault("growth", deepcopy(DEFAULT_PERSONALITY_TEMPLATE["growth"]))
        max_allowed = growth.get("max_level", DEFAULT_PERSONALITY_TEMPLATE["growth"]["max_level"])
        if growth.get("level", 0) > max_allowed:
            warnings.append("growth_level_clamped")
            growth["level"] = max_allowed

        # Tone / verbosity sanity checks
        if p.get("tone") not in ("neutral", "friendly", "professional", "curt", "playful"):
            warnings.append("tone_reset")
            p["tone"] = DEFAULT_PERSONALITY_TEMPLATE["tone"]

        if p.get("verbosity") not in ("terse", "balanced", "verbose"):
            warnings.append("verbosity_reset")
            p["verbosity"] = DEFAULT_PERSONALITY_TEMPLATE["verbosity"]

        entry["updated_at"] = self._now()
        self._save_db()
        return warnings

    # ---------- Import / Export ----------
    def export_personality(self, subchat_id: str, path: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
        entry = self._db.get(subchat_id)
        if not entry:
            return False, "subchat_not_found"
        path = Path(path) if path else (Path.cwd() / f"{subchat_id}_personality.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2, ensure_ascii=False)
            return True, str(path)
        except Exception as e:
            return False, str(e)

    def import_personality(self, path: Path, overwrite: bool = False) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return {"status": "error", "error": f"load_failed: {e}"}

        sid = data.get("id") or str(uuid.uuid4())
        if sid in self._db and not overwrite:
            return {"status": "error", "error": "exists", "id": sid}

        # sanitize: strip protected traits
        data_personality = data.get("personality", {})
        data_personality = self._filter_protected_traits(data_personality)
        data["personality"] = data_personality
        data.setdefault("created_at", self._now())
        data["updated_at"] = self._now()
        self._db[sid] = data
        self._save_db()
        return {"status": "ok", "id": sid}

    # ---------- Introspection ----------
    def describe(self, subchat_id: str) -> Dict[str, Any]:
        """
        Return a short human-friendly description of the subchat personality and state.
        """
        entry = self._db.get(subchat_id)
        if not entry:
            return {"status": "error", "error": "subchat_not_found"}

        p = entry.get("personality", {})
        desc = {
            "id": subchat_id,
            "parent": entry.get("parent"),
            "name": p.get("name"),
            "description": p.get("description"),
            "tone": p.get("tone"),
            "verbosity": p.get("verbosity"),
            "growth": p.get("growth"),
            "last_updated": entry.get("updated_at")
        }
        return {"status": "ok", "summary": desc}

    # ---------- Safe removal ----------
    def remove_subchat(self, subchat_id: str, allow_delete_protected: bool = False) -> Dict[str, Any]:
        """
        Remove a subchat entry entirely. This does not remove parent.
        """
        if subchat_id not in self._db:
            return {"status": "error", "error": "subchat_not_found"}

        # Extra safety: do not allow delete of protected IDs unless flag set
        if not allow_delete_protected and subchat_id in PROTECTED_TRAITS:
            return {"status": "error", "error": "protected_subchat"}

        self._db.pop(subchat_id)
        self._save_db()
        return {"status": "ok", "removed": subchat_id}