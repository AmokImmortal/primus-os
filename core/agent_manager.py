# core/agent_manager.py
"""
PRIMUS Core: Agent Manager

Responsibilities:
- Discover agents in /agents
- Load per-agent configs (agents/<AgentName>/config.json) and provide defaults
- Enforce permissions (read, write, internet, run_commands, modify_core)
- Enforce personality growth limits (personality_growth section)
- Provide a capability ticket system for controlled inter-agent access
- Provide safe file access helpers (prevent writes outside agent folder)
- Propose/approve mechanism for agent-requested changes (manual approval required)
- Logging of actions and policy violations

Design choices:
- Config files are JSON inside each agent folder.
- No agent may write outside its own folder unless the agent config explicitly allows it.
- Major system changes must be applied via "proposal" and flagged for manual approval.
- This module returns structured dicts (status/info/error) so other modules can handle responses.
"""

import json
import os
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

# -----------------------
# Utilities & Constants
# -----------------------

MODULE_NAME = "core.agent_manager"

def _now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def _safe_json_dump(path: Path, obj: Any):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

# -----------------------
# System Root Detection
# -----------------------

def find_system_root() -> Path:
    """
    Attempt to locate the PRIMUS system root directory.
    1) If configs/system_paths.json exists in cwd or parents, use that parent.
    2) Otherwise assume two levels up from this file is system root.
    """
    cur = Path.cwd()
    for p in [cur] + list(cur.parents):
        candidate = p / "configs" / "system_paths.json"
        if candidate.exists():
            return p
    # fallback: assume repository layout: core/ -> system root parent
    here = Path(__file__).resolve()
    return here.parents[2]

SYSTEM_ROOT = find_system_root()
AGENTS_DIR = SYSTEM_ROOT / "agents"
SYSTEM_LOGS_DIR = SYSTEM_ROOT / "system" / "system_logs"
SYSTEM_LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = SYSTEM_LOGS_DIR / "agent_manager.log"
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# -----------------------
# Default agent config
# -----------------------

DEFAULT_AGENT_CONFIG = {
    "name": None,
    "version": "0.1",
    "description": "",
    # Permissions: read/write/internet/run_commands/modify_core (booleans)
    "permissions": {
        "read_system_memory": False,
        "read_other_agents": False,
        "write_own_folder": True,
        "write_outside": False,
        "access_internet": False,
        "run_shell_commands": False,
        "modify_core": False
    },
    # Personality / growth rules
    "personality": {
        "traits": {
            "friendliness": 0.6,
            "creativity": 0.5,
            "aggression": 0.0,
            "confidence": 0.5
        }
    },
    "personality_growth": {
        "allowed_traits": ["friendliness", "creativity", "confidence"],
        "restricted_traits": ["aggression", "disobedience"],
        "growth_rate": 0.05,
        "max_drift": 0.3
    },
    "storage": {
        "root": None
    }
}

# -----------------------
# Agent Manager Class
# -----------------------

class AgentManager:
    def __init__(self, agents_dir: Optional[Path] = None):
        self.agents_dir = (agents_dir or AGENTS_DIR)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.tickets: Dict[str, Dict[str, Any]] = {}
        self.proposals: Dict[str, Dict[str, Any]] = {}
        logging.info("[%s] Initialized. AGENTS_DIR=%s", MODULE_NAME, str(self.agents_dir))

    # -----------------------
    # Agent discovery & config
    # -----------------------
    def list_agents(self) -> List[str]:
        names = []
        for entry in sorted(self.agents_dir.iterdir()):
            if entry.is_dir():
                names.append(entry.name)
        return names

    def _agent_dir(self, agent_name: str) -> Path:
        return self.agents_dir / agent_name

    def _config_path(self, agent_name: str) -> Path:
        return self._agent_dir(agent_name) / "config.json"

    def load_agent_config(self, agent_name: str) -> Dict[str, Any]:
        agent_dir = self._agent_dir(agent_name)
        cfg_path = self._config_path(agent_name)
        if not agent_dir.exists():
            agent_dir.mkdir(parents=True, exist_ok=True)
        if cfg_path.exists():
            try:
                with cfg_path.open("r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg.setdefault("storage", {})
                cfg["storage"].setdefault("root", str(agent_dir))
                return cfg
            except Exception as e:
                logging.error("[%s] Failed to load config for %s: %s", MODULE_NAME, agent_name, e)

        cfg = DEFAULT_AGENT_CONFIG.copy()
        cfg["name"] = agent_name
        cfg["storage"] = {"root": str(agent_dir)}
        _safe_json_dump(cfg_path, cfg)
        logging.info("[%s] Created default config for agent '%s'", MODULE_NAME, agent_name)
        return cfg

    def save_agent_config(self, agent_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        cfg_path = self._config_path(agent_name)
        try:
            cfg.setdefault("storage", {})
            cfg["storage"]["root"] = str(self._agent_dir(agent_name))
            _safe_json_dump(cfg_path, cfg)
            logging.info("[%s] Saved config for agent '%s'", MODULE_NAME, agent_name)
            return {"status": "ok"}
        except Exception as e:
            logging.exception("[%s] Failed to save config for %s", MODULE_NAME, agent_name)
            return {"status": "error", "error": str(e)}

    # -----------------------
    # Permission checks
    # -----------------------
    def _has_permission(self, agent_name: str, permission: str) -> bool:
        cfg = self.load_agent_config(agent_name)
        perms = cfg.get("permissions", {})
        return bool(perms.get(permission, False))

    def can_read(self, agent_name: str, target_path: str) -> Dict[str, Any]:
        try:
            target = Path(target_path).resolve()
        except Exception as e:
            return {"status": "error", "error": "invalid_target", "detail": str(e)}

        agent_cfg = self.load_agent_config(agent_name)
        agent_root = Path(agent_cfg["storage"]["root"]).resolve()

        if agent_root in target.parents or agent_root == target:
            return {"status": "ok", "allowed": True, "reason": "own_folder"}

        if self._is_subdir_of_agents_dir(target):
            if self._has_permission(agent_name, "read_other_agents"):
                return {"status": "ok", "allowed": True, "reason": "read_other_agents_allowed"}
            else:
                return {"status": "error", "allowed": False, "error": "permission_denied"}

        if self._is_system_sensitive(target):
            if self._has_permission(agent_name, "read_system_memory"):
                return {"status": "ok", "allowed": True, "reason": "read_system_memory_allowed"}
            else:
                return {"status": "error", "allowed": False, "error": "permission_denied"}

        return {"status": "ok", "allowed": True, "reason": "default_allow_read"}

    def can_write(self, agent_name: str, target_path: str) -> Dict[str, Any]:
        try:
            target = Path(target_path).resolve()
        except Exception as e:
            return {"status": "error", "error": "invalid_target", "detail": str(e)}

        agent_cfg = self.load_agent_config(agent_name)
        agent_root = Path(agent_cfg["storage"]["root"]).resolve()

        if agent_root in target.parents or agent_root == target:
            if self._has_permission(agent_name, "write_own_folder"):
                return {"status": "ok", "allowed": True, "reason": "own_folder"}
            else:
                return {"status": "error", "allowed": False}

        if self._is_system_sensitive(target):
            if self._has_permission(agent_name, "modify_core"):
                return {"status": "ok", "allowed": True, "reason": "modify_core_allowed"}
            else:
                return {"status": "error", "allowed": False}

        if self._is_subdir_of_agents_dir(target) or self._is_subdir_of_system(target):
            if self._has_permission(agent_name, "write_outside"):
                return {"status": "ok", "allowed": True}
            else:
                return {"status": "error", "allowed": False}

        if self._has_permission(agent_name, "write_outside"):
            return {"status": "ok", "allowed": True}

        return {"status": "error", "allowed": False}

    def can_access_internet(self, agent_name: str) -> bool:
        return self._has_permission(agent_name, "access_internet")

    # -----------------------
    # Helpers
    # -----------------------
    def _is_subdir_of_agents_dir(self, path: Path) -> bool:
        try:
            path = path.resolve()
            return AGENTS_DIR.resolve() in path.parents or AGENTS_DIR.resolve() == path
        except Exception:
            return False

    def _is_subdir_of_system(self, path: Path) -> bool:
        try:
            return SYSTEM_ROOT.resolve() in path.parents or SYSTEM_ROOT.resolve() == path
        except Exception:
            return False

    def _is_system_sensitive(self, path: Path) -> bool:
        try:
            path = path.resolve()
            sensitive = {"configs", "core", "PRIMUS_master", "PRIMUS_kernel", "system"}
            for name in sensitive:
                if (SYSTEM_ROOT / name).resolve() in path.parents or (SYSTEM_ROOT / name).resolve() == path:
                    return True
            return False
        except Exception:
            return False

    # -----------------------
    # Safe file operations
    # -----------------------
    def safe_write_file(self, agent_name: str, relative_path: str, content: str) -> Dict[str, Any]:
        try:
            target = Path(relative_path)
            if target.is_absolute():
                target = target.resolve()
            else:
                target = target.resolve()
        except Exception as e:
            return {"status": "error", "error": "invalid_path", "detail": str(e)}

        check = self.can_write(agent_name, str(target))
        if check.get("allowed"):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("w", encoding="utf-8") as f:
                    f.write(content)
                logging.info("[%s] Agent '%s' wrote file: %s", MODULE_NAME, agent_name, str(target))
                return {"status": "ok", "path": str(target)}
            except Exception as e:
                logging.exception("[%s] Write failed for '%s' -> %s", MODULE_NAME, agent_name, e)
                return {"status": "error", "error": "write_failed", "detail": str(e)}
        else:
            return {"status": "error", "error": "permission_denied", "detail": check}

    def safe_read_file(self, agent_name: str, path: str) -> Dict[str, Any]:
        try:
            target = Path(path).resolve()
        except Exception as e:
            return {"status": "error", "error": "invalid_path", "detail": str(e)}

        check = self.can_read(agent_name, str(target))
        if check.get("allowed"):
            try:
                with target.open("r", encoding="utf-8", errors="ignore") as f:
                    data = f.read()
                logging.info("[%s] Agent '%s' read file: %s", MODULE_NAME, agent_name, str(target))
                return {"status": "ok", "content": data}
            except Exception as e:
                return {"status": "error", "error": "read_failed", "detail": str(e)}
        else:
            return {"status": "error", "error": "permission_denied", "detail": check}

    # -----------------------
    # Personality growth / proposals
    # -----------------------
    def propose_personality_update(self, agent_name: str, trait_changes: Dict[str, float], reason: str) -> Dict[str, Any]:
        cfg = self.load_agent_config(agent_name)
        growth_cfg = cfg.get("personality_growth", {})
        allowed = set(growth_cfg.get("allowed_traits", []))
        restricted = set(growth_cfg.get("restricted_traits", []))
        baseline = cfg.get("personality", {}).get("traits", {})

        max_step = float(growth_cfg.get("growth_rate", 0.05))
        new_traits = dict(baseline)

        for k, delta in trait_changes.items():
            if k not in baseline:
                return {"status": "error", "error": "invalid_trait"}
            proposed = float(delta)
            if proposed < 0.0 or proposed > 1.0:
                return {"status": "error", "error": "trait_value_out_of_bounds"}
            step = abs(proposed - float(baseline.get(k, 0.0)))
            if step > max_step:
                return {"status": "error", "error": "exceeds_growth_rate"}
            new_traits[k] = proposed

        max_drift = float(growth_cfg.get("max_drift", 0.3))
        for k, v in new_traits.items():
            drift = abs(v - float(baseline.get(k, 0.0)))
            if drift > max_drift and k in restricted:
                return {"status": "error", "error": "exceeds_max_drift_restricted"}

        pid = str(uuid.uuid4())
        proposal = {
            "id": pid,
            "agent": agent_name,
            "type": "personality_update",
            "proposed_traits": new_traits,
            "baseline": baseline,
            "reason": reason,
            "created_at": _now_ts(),
            "approved": False,
            "approved_at": None,
            "approved_by": None
        }

        self.proposals[pid] = proposal
        proposal_path = self._agent_dir(agent_name) / f"proposal_{pid}.json"
        _safe_json_dump(proposal_path, proposal)
        return {"status": "ok", "proposal": proposal}

    def approve_proposal(self, proposal_id: str, approver: str) -> Dict[str, Any]:
        p = self.proposals.get(proposal_id)
        if not p:
            return {"status": "error", "error": "proposal_not_found"}
        if p.get("approved"):
            return {"status": "error", "error": "already_approved"}

        agent_name = p["agent"]
        cfg = self.load_agent_config(agent_name)

        cfg.setdefault("personality", {})["traits"] = p["proposed_traits"]
        save_res = self.save_agent_config(agent_name, cfg)
        if save_res.get("status") != "ok":
            return save_res

        p["approved"] = True
        p["approved_at"] = _now_ts()
        p["approved_by"] = approver

        proposal_path = self._agent_dir(agent_name) / f"proposal_{proposal_id}.json"
        _safe_json_dump(proposal_path, p)
        return {"status": "ok", "proposal_id": proposal_id}

    # -----------------------
    # Capability Tickets
    # -----------------------
    def issue_ticket(self, issuer_agent: str, target_agent: str, scope: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        if not self._has_permission(issuer_agent, "read_other_agents"):
            return {"status": "error", "error": "issuer_not_permitted"}

        tid = str(uuid.uuid4())
        ticket = {
            "id": tid,
            "issuer": issuer_agent,
            "target": target_agent,
            "scope": scope,
            "issued_at": _now_ts(),
            "expires_at": _now_ts(),
            "ttl_seconds": ttl_seconds,
            "revoked": False
        }
        ticket["expires_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + ttl_seconds))
        self.tickets[tid] = ticket
        return {"status": "ok", "ticket": ticket}

    def validate_ticket(self, ticket_id: str) -> bool:
        t = self.tickets.get(ticket_id)
        if not t:
            return False
        if t.get("revoked"):
            return False
        exp = time.strptime(t["expires_at"], "%Y-%m-%d %H:%M:%S")
        if time.mktime(exp) < time.time():
            return False
        return True

    def revoke_ticket(self, ticket_id: str) -> Dict[str, Any]:
        t = self.tickets.get(ticket_id)
        if not t:
            return {"status": "error", "error": "ticket_not_found"}
        t["revoked"] = True
        return {"status": "ok"}

    # -----------------------
    # Status
    # -----------------------
    def agent_status(self, agent_name: str) -> Dict[str, Any]:
        try:
            cfg = self.load_agent_config(agent_name)
            info = {
                "name": cfg.get("name"),
                "version": cfg.get("version"),
                "permissions": cfg.get("permissions"),
                "personality": cfg.get("personality", {}).get("traits", {}),
                "storage_root": cfg.get("storage", {}).get("root")
            }
            return {"status": "ok", "agent": info}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_proposals(self) -> List[Dict[str, Any]]:
        return list(self.proposals.values())

    def list_tickets(self) -> List[Dict[str, Any]]:
        return list(self.tickets.values())

# -----------------------
# Script test
# -----------------------
if __name__ == "__main__":
    am = AgentManager()
    print("SYSTEM_ROOT:", SYSTEM_ROOT)
    print("AGENTS:", am.list_agents())
    agents = am.list_agents()
    if not agents:
        am.load_agent_config("DemoAgent")
        agents = am.list_agents()
    agent = agents[0]
    print("STATUS:", am.agent_status(agent))
    p = am.propose_personality_update(agent, {"friendliness": 0.7}, "test")
    print("PROPOSAL:", p)
    if p.get("status") == "ok":
        pid = p["proposal"]["id"]
        print("APPROVE:", am.approve_proposal(pid, "admin"))