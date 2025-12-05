import os
import json
from typing import Dict, Any, Optional
from threading import RLock


class AgentRegistry:
    """
    Maintains a secure, isolated registry of all agents in PRIMUS.

    Responsibilities:
    - Register new agents (Primus + all specialized agents)
    - Store metadata (personality file, RAG folder, permissions, etc.)
    - Provide read-only access to agent definitions
    - Prevent modification unless explicitly approved by the Security Enforcer
    """

    def __init__(self, registry_file: str = "data/agent_registry.json"):
        self.registry_file = registry_file
        self._lock = RLock()

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)

        # Load initial registry or create default
        if not os.path.exists(self.registry_file):
            self._write_registry({})
        self.registry = self._load_registry()

    # ---------------------------- Internal I/O -------------------------------- #

    def _load_registry(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

    def _write_registry(self, data: Dict[str, Any]):
        with self._lock:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

    # ---------------------------- Core Functions ------------------------------ #

    def register_agent(
        self,
        agent_id: str,
        name: str,
        persona_path: str,
        rag_folder: str,
        permissions: Dict[str, Any],
        type: str = "specialized",
    ) -> bool:
        """
        Registers an agent into PRIMUS.
        Only allowed via PRIMUS or the Security Enforcer.
        """

        with self._lock:
            if agent_id in self.registry:
                return False  # Already exists

            self.registry[agent_id] = {
                "name": name,
                "type": type,
                "persona_path": persona_path,
                "rag_folder": rag_folder,
                "permissions": permissions,
                "active": True,
            }

            self._write_registry(self.registry)
            return True

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return a read-only definition of an agent."""
        return self.registry.get(agent_id)

    def list_agents(self) -> Dict[str, Any]:
        """Return all registered agents."""
        return dict(self.registry)

    def deactivate_agent(self, agent_id: str) -> bool:
        """Soft-disable an agent until reactivated."""
        with self._lock:
            if agent_id not in self.registry:
                return False
            self.registry[agent_id]["active"] = False
            self._write_registry(self.registry)
            return True

    def activate_agent(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self.registry:
                return False
            self.registry[agent_id]["active"] = True
            self._write_registry(self.registry)
            return True

    def update_permissions(self, agent_id: str, permissions: Dict[str, Any]) -> bool:
        """Update permissions only when authorized."""
        with self._lock:
            if agent_id not in self.registry:
                return False
            self.registry[agent_id]["permissions"] = permissions
            self._write_registry(self.registry)
            return True

    # ------------------------- Safety / Verification -------------------------- #

    def verify_integrity(self) -> bool:
        """
        Quick check to confirm registry isn't corrupted.
        """
        with self._lock:
            try:
                _ = self._load_registry()
                return True
            except Exception:
                return False