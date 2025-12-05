# core/memory.py
# PRIMUS OS — Unified Memory Manager (JSON-Based)
# Handles: system memory, agent memory, personality profiles, inter-agent read access

import json
import os
from typing import Dict, Any, Optional

class MemoryManager:
    """
    Centralized JSON-based memory system for:
        - System/Core memory (read/write allowed only from PRIMUS core)
        - Agent memory (persistent, isolated, personality-aware)
        - Inter-agent READ-ONLY access
        - Agent personality growth (restricted)
        - Sub-chat inheritance
    """

    def __init__(self, memory_root: str = "memory"):
        self.memory_root = memory_root
        self.system_memory_path = os.path.join(memory_root, "system_memory.json")
        self.agents_dir = os.path.join(memory_root, "agents")

        os.makedirs(self.memory_root, exist_ok=True)
        os.makedirs(self.agents_dir, exist_ok=True)

        # Ensure system memory file exists
        if not os.path.exists(self.system_memory_path):
            self._write_json(self.system_memory_path, {"system_notes": {}, "boot_history": []})

    # -------------------------------------------------
    # Utility JSON I/O
    # -------------------------------------------------

    def _read_json(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, data: Dict[str, Any]):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # -------------------------------------------------
    # System/Core Memory  (ONLY PRIMUS CORE CAN WRITE)
    # -------------------------------------------------

    def read_system_memory(self) -> Dict[str, Any]:
        return self._read_json(self.system_memory_path)

    def write_system_memory(self, new_data: Dict[str, Any]):
        """Core-only write. Agents must NEVER call this."""
        self._write_json(self.system_memory_path, new_data)

    def append_boot_log(self, status: str):
        """Adds logs from the PRIMUS OS self-test results."""
        sysmem = self.read_system_memory()
        sysmem.setdefault("boot_history", []).append({"status": status})
        self.write_system_memory(sysmem)

    # -------------------------------------------------
    # Agent Memory
    # -------------------------------------------------

    def _agent_path(self, agent_name: str) -> str:
        return os.path.join(self.agents_dir, f"{agent_name}.json")

    def ensure_agent(self, agent_name: str):
        """Creates the agent memory file if it does not exist."""
        path = self._agent_path(agent_name)
        if not os.path.exists(path):
            data = {
                "personality_profile": {
                    "name": agent_name,
                    "traits": {},
                    "growth_history": []
                },
                "memory": {
                    "notes": [],
                    "knowledge": {}
                },
                "subchats": {}
            }
            self._write_json(path, data)

    def read_agent_memory(self, agent_name: str) -> Dict[str, Any]:
        self.ensure_agent(agent_name)
        return self._read_json(self._agent_path(agent_name))

    def write_agent_memory(self, agent_name: str, new_data: Dict[str, Any]):
        """Agents can write ONLY to their own memory files."""
        self.ensure_agent(agent_name)
        self._write_json(self._agent_path(agent_name), new_data)

    # -------------------------------------------------
    # Agent Personality Handling
    # -------------------------------------------------

    def update_agent_personality(self, agent_name: str, changes: Dict[str, Any]):
        """
        Controlled personality growth.
        Agents may evolve based on user approval or system-defined rules.
        """
        agent_data = self.read_agent_memory(agent_name)

        traits = agent_data["personality_profile"].get("traits", {})
        for key, value in changes.items():
            traits[key] = value

        # Log personality update
        agent_data["personality_profile"]["growth_history"].append(changes)

        # Save updates
        agent_data["personality_profile"]["traits"] = traits
        self.write_agent_memory(agent_name, agent_data)

    # -------------------------------------------------
    # Sub-Chat Inheritance
    # -------------------------------------------------

    def create_subchat(self, agent_name: str, subchat_id: str):
        """
        Sub-chats do NOT have personality.
        They inherit temporary working memory from the main agent.
        """
        agent_data = self.read_agent_memory(agent_name)
        agent_data.setdefault("subchats", {})

        agent_data["subchats"][subchat_id] = {
            "context": [],
            "temp_memory": {}
        }

        self.write_agent_memory(agent_name, agent_data)

    def read_subchat(self, agent_name: str, subchat_id: str) -> Dict[str, Any]:
        agent_data = self.read_agent_memory(agent_name)
        return agent_data.get("subchats", {}).get(subchat_id, {})

    def write_subchat(self, agent_name: str, subchat_id: str, new_data: Dict[str, Any]):
        agent_data = self.read_agent_memory(agent_name)
        agent_data["subchats"][subchat_id] = new_data
        self.write_agent_memory(agent_name, agent_data)

    # -------------------------------------------------
    # Inter-Agent READ-ONLY Access
    # -------------------------------------------------

    def read_other_agent(self, requesting_agent: str, target_agent: str) -> Optional[Dict[str, Any]]:
        """
        Agents can ONLY READ other agent memory.
        Must never modify.
        """
        if requesting_agent == target_agent:
            return self.read_agent_memory(target_agent)

        target_path = self._agent_path(target_agent)
        if not os.path.exists(target_path):
            return None

        return self._read_json(target_path)

    # -------------------------------------------------
    # Knowledge Append Helpers
    # -------------------------------------------------

    def append_agent_note(self, agent_name: str, note: str):
        data = self.read_agent_memory(agent_name)
        data["memory"].setdefault("notes", []).append(note)
        self.write_agent_memory(agent_name, data)

    def add_agent_knowledge(self, agent_name: str, key: str, value: Any):
        data = self.read_agent_memory(agent_name)
        data["memory"].setdefault("knowledge", {})[key] = value
        self.write_agent_memory(agent_name, data)