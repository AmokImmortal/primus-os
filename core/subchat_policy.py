"""
/core/subchat_policy.py

Subchat Policy Engine for PRIMUS OS
- Manage policies for subchat access, actions, and special constraints (passwords, privacy).
- Store policies in JSON under core/policies/subchat_policies.json
- Provide evaluation hooks used by SubchatAccessControl / SubchatManager.

Policy schema (example):
{
  "<subchat_id>": {
      "id": "<subchat_id>",
      "name": "Business Ops — Mobile Detailing",
      "owner": "user:amoki",
      "private": true,
      "password_protected": true,
      "password_hash": "<sha256>",
      "security_questions": [
          {"q": "mother_maiden", "answer_hash": "<sha256>"},
          ...
      ],
      "allowed_agents": ["MobileDetailAgent"],
      "allowed_users": ["user:amoki"],
      "allow_agent_to_agent": false,
      "rag_read": ["own", "global"],  # options: "none", "own", "global", "all"
      "rag_write": false,
      "max_concurrent_workers": 2,
      "notes": "Sandbox captain's log restrictions"
  },
  ...
}

Usage:
  store = PolicyStore()
  evaluator = PolicyEvaluator(store)
  evaluator.is_action_allowed(subchat_id, actor, action, context={})
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

LOG = logging.getLogger("subchat_policy")
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[subchat_policy] %(levelname)s: %(message)s"))
    LOG.addHandler(ch)

# Paths
CORE_DIR = Path(__file__).resolve().parents[1]
POLICY_DIR = CORE_DIR / "policies"
POLICY_FILE = POLICY_DIR / "subchat_policies.json"


def _hash_secret(secret: str) -> str:
    """Return a stable SHA256 hex digest for secrets (passwords / answers)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class PolicyStore:
    """Persistence layer for subchat policies."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or POLICY_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._policies: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._policies = json.load(f)
                LOG.info("Loaded subchat policies from disk.")
            except Exception as e:
                LOG.error("Failed to load policies: %s", e)
                self._policies = {}
        else:
            self._policies = {}
            self.save()  # create file

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._policies, f, indent=2, ensure_ascii=False)
            LOG.info("Saved subchat policies to disk.")
        except Exception as e:
            LOG.error("Failed to save policies: %s", e)

    def get_policy(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        return self._policies.get(subchat_id)

    def list_policies(self) -> List[Dict[str, Any]]:
        return list(self._policies.values())

    def set_policy(self, subchat_id: str, policy: Dict[str, Any]) -> None:
        policy = dict(policy)
        policy["id"] = subchat_id
        self._policies[subchat_id] = policy
        self.save()

    def remove_policy(self, subchat_id: str) -> bool:
        if subchat_id in self._policies:
            del self._policies[subchat_id]
            self.save()
            return True
        return False

    def ensure_default_policy(self, subchat_id: str, owner: str) -> Dict[str, Any]:
        """Create minimal default policy if missing and return it."""
        pol = self.get_policy(subchat_id)
        if pol:
            return pol
        default = {
            "id": subchat_id,
            "name": subchat_id,
            "owner": owner,
            "private": True,
            "password_protected": False,
            "password_hash": None,
            "security_questions": [],
            "allowed_agents": [],
            "allowed_users": [owner],
            "allow_agent_to_agent": False,
            "rag_read": "own",
            "rag_write": False,
            "max_concurrent_workers": 1,
            "notes": ""
        }
        self.set_policy(subchat_id, default)
        return default


class PolicyEvaluator:
    """Evaluates whether an actor may perform an action in a subchat."""

    def __init__(self, store: PolicyStore):
        self.store = store

    # -- Helpers --
    def _get_policy(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_policy(subchat_id)

    def _is_owner(self, policy: Dict[str, Any], actor: str) -> bool:
        return actor == policy.get("owner")

    def _actor_type(self, actor: str) -> str:
        """
        Actor string convention:
          - user:<username>
          - agent:<AgentName>
        """
        if actor.startswith("user:"):
            return "user"
        if actor.startswith("agent:"):
            return "agent"
        return "unknown"

    # -- Public API --
    def is_action_allowed(self, subchat_id: str, actor: str, action: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate if `actor` may perform `action` in subchat `subchat_id`.
        action examples: "read", "write", "join", "spawn_worker", "query_rag", "modify_policy"
        Returns dict: {"allowed": bool, "reason": str}
        """
        context = context or {}
        policy = self._get_policy(subchat_id)
        if policy is None:
            LOG.info("No policy for subchat '%s' — denying by default.", subchat_id)
            return {"allowed": False, "reason": "no_policy"}

        actor_type = self._actor_type(actor)

        # Owners may do everything except bypass system-level protections
        if self._is_owner(policy, actor):
            return {"allowed": True, "reason": "owner"}

        # Handle password-protected join
        if action == "join":
            if policy.get("password_protected"):
                supplied = context.get("password")
                if not supplied:
                    return {"allowed": False, "reason": "password_required"}
                if _hash_secret(supplied) != policy.get("password_hash"):
                    return {"allowed": False, "reason": "invalid_password"}
            # If not password-protected, check allowed_users / allowed_agents
            if actor_type == "user":
                if actor in policy.get("allowed_users", []):
                    return {"allowed": True, "reason": "user_allowed"}
                else:
                    return {"allowed": False, "reason": "user_not_allowed"}
            elif actor_type == "agent":
                if actor.split(":", 1)[1] in policy.get("allowed_agents", []):
                    return {"allowed": True, "reason": "agent_allowed"}
                else:
                    return {"allowed": False, "reason": "agent_not_allowed"}
            else:
                return {"allowed": False, "reason": "unknown_actor"}

        # Read/write/query actions
        if action in ("read", "query_rag"):
            rag_policy = policy.get("rag_read", "none")
            # Interpret rag_read values:
            # "none" -> no RAG access, "own" -> only subchat's own RAG,
            # "global" -> system global RAG allowed, "all" -> full RAG access
            if rag_policy == "none":
                return {"allowed": False, "reason": "rag_disabled"}
            if actor_type == "agent":
                # agents must be explicitly allowed unless rag_read == all
                if rag_policy == "all":
                    return {"allowed": True, "reason": "rag_all"}
                if rag_policy == "global":
                    return {"allowed": True, "reason": "rag_global"}
                if rag_policy == "own":
                    # agents may read own RAG only if agent belongs to subchat
                    agent_name = actor.split(":", 1)[1]
                    if agent_name in policy.get("allowed_agents", []):
                        return {"allowed": True, "reason": "rag_own_agent"}
                    return {"allowed": False, "reason": "rag_own_only"}
            else:
                # user access: check allowed_users
                if actor in policy.get("allowed_users", []):
                    return {"allowed": True, "reason": "user_rag_allowed"}
                return {"allowed": False, "reason": "user_not_allowed"}

        if action == "write":
            if policy.get("rag_write"):
                actor_allowed = (actor_type == "user" and actor in policy.get("allowed_users", [])) or (actor_type == "agent" and actor.split(":", 1)[1] in policy.get("allowed_agents", []))
                if actor_allowed:
                    return {"allowed": True, "reason": "write_allowed"}
                return {"allowed": False, "reason": "write_not_allowed"}
            return {"allowed": False, "reason": "write_disabled"}

        if action == "spawn_worker":
            # Enforce max_concurrent_workers (context may provide current count)
            max_workers = int(policy.get("max_concurrent_workers", 1) or 1)
            current = int(context.get("current_workers", 0))
            if current >= max_workers:
                return {"allowed": False, "reason": "max_workers_exceeded"}
            # only allow agents (or users with permission) to spawn workers
            if actor_type == "agent":
                if actor.split(":", 1)[1] in policy.get("allowed_agents", []):
                    return {"allowed": True, "reason": "agent_allowed_spawn"}
                return {"allowed": False, "reason": "agent_not_allowed_spawn"}
            if actor_type == "user" and actor in policy.get("allowed_users", []):
                return {"allowed": True, "reason": "user_allowed_spawn"}
            return {"allowed": False, "reason": "not_permitted_to_spawn"}

        if action == "agent_to_agent":
            # Only allow if policy explicitly enables agent->agent and both agents are permitted
            if not policy.get("allow_agent_to_agent", False):
                return {"allowed": False, "reason": "agent_to_agent_disabled"}
            src = context.get("source_agent")
            dst = context.get("target_agent")
            if not src or not dst:
                return {"allowed": False, "reason": "missing_agents"}
            allowed_agents = policy.get("allowed_agents", [])
            if src not in allowed_agents or dst not in allowed_agents:
                return {"allowed": False, "reason": "agent_not_in_allowed_list"}
            return {"allowed": True, "reason": "agent_to_agent_allowed"}

        if action == "modify_policy":
            # Only owner may modify; administrators may be added in allowed_users
            return {"allowed": False, "reason": "only_owner_can_modify"}

        # Default deny
        return {"allowed": False, "reason": "action_not_recognized"}

    # -- Utilities for policy management --
    def set_password(self, subchat_id: str, password: Optional[str]) -> bool:
        policy = self._get_policy(subchat_id)
        if policy is None:
            LOG.error("Cannot set password; policy not found: %s", subchat_id)
            return False
        if password is None:
            policy["password_protected"] = False
            policy["password_hash"] = None
        else:
            policy["password_protected"] = True
            policy["password_hash"] = _hash_secret(password)
        self.store.set_policy(subchat_id, policy)
        LOG.info("Password updated for subchat '%s' (protected=%s).", subchat_id, policy["password_protected"])
        return True

    def verify_security_question(self, subchat_id: str, question_key: str, answer: str) -> bool:
        policy = self._get_policy(subchat_id)
        if not policy:
            return False
        for q in policy.get("security_questions", []):
            if q.get("q") == question_key:
                return _hash_secret(answer) == q.get("answer_hash")
        return False

    def add_security_question(self, subchat_id: str, question_key: str, answer: str) -> bool:
        policy = self._get_policy(subchat_id)
        if not policy:
            return False
        policy.setdefault("security_questions", [])
        policy["security_questions"].append({
            "q": question_key,
            "answer_hash": _hash_secret(answer)
        })
        self.store.set_policy(subchat_id, policy)
        return True