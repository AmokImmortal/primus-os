# core/persona.py
# Handles loading, storing, modifying, and applying personalities
# for PRIMUS and all specialized agents.

import json
import os
from typing import Dict, Any

PERSONALITY_FILE = os.path.join("system", "personality.json")


class PersonalityManager:
    """
    PersonalityManager loads and manages personalities for PRIMUS and agents.
    Handles personality growth, restrictions, permissions, and safe updates.
    """

    def __init__(self):
        self.data = self._load_json()

    # ---------------------------------------
    # JSON MANAGEMENT
    # ---------------------------------------
    def _load_json(self) -> Dict[str, Any]:
        if not os.path.exists(PERSONALITY_FILE):
            raise FileNotFoundError(f"Missing personality file: {PERSONALITY_FILE}")

        with open(PERSONALITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self):
        with open(PERSONALITY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # ---------------------------------------
    # PRIMUS PERSONALITY
    # ---------------------------------------
    def get_primus_personality(self) -> Dict[str, Any]:
        return self.data.get("primus", {})

    # ---------------------------------------
    # AGENT DEFAULT PERSONALITY TEMPLATE
    # ---------------------------------------
    def get_default_agent_template(self) -> Dict[str, Any]:
        return self.data.get("agent_defaults", {}).get("personality_template", {})

    def get_default_agent_permissions(self) -> Dict[str, Any]:
        return self.data.get("agent_defaults", {}).get("permissions", {})

    # ---------------------------------------
    # INITIALIZE A NEW AGENT PERSONALITY
    # ---------------------------------------
    def create_agent_personality(self, agent_name: str) -> Dict[str, Any]:
        if "agents" not in self.data:
            self.data["agents"] = {}

        if agent_name in self.data["agents"]:
            return self.data["agents"][agent_name]

        # Clone the baseline template
        template = self.get_default_agent_template()
        permissions = self.get_default_agent_permissions()

        new_personality = {
            "name": agent_name,
            "description": template.get("description", ""),
            "traits": template.get("traits", {}),
            "growth_rules": template.get("growth_rules", {}),
            "permissions": permissions,
            "memory_policy": {
                "allow_write": True,
                "allow_read": True,
                "persistent_growth": True
            }
        }

        self.data["agents"][agent_name] = new_personality
        self.save()

        return new_personality

    # ---------------------------------------
    # GET PERSONALITY FOR ANY AGENT
    # ---------------------------------------
    def get_agent_personality(self, agent_name: str) -> Dict[str, Any]:
        agents = self.data.get("agents", {})
        return agents.get(agent_name)

    # ---------------------------------------
    # PERSONALITY GROWTH
    # ---------------------------------------
    def apply_personality_growth(self, personality: Dict[str, Any], feedback: Dict[str, float]):
        """
        feedback example:
        {
            "warmth": +0.03,
            "directness": -0.01,
            "curiosity": +0.02
        }
        """

        if not personality.get("growth_rules", {}).get("enabled", False):
            return personality

        traits = personality.get("traits", {})
        max_drift = personality["growth_rules"].get("max_drift_from_template", 0.25)

        # Load template for comparison
        template = None
        if personality.get("name") == "PRIMUS":
            template = self.get_primus_personality().get("traits", {})
        else:
            template = self.get_default_agent_template().get("traits", {})

        # Apply modifications safely
        for trait, delta in feedback.items():
            if trait not in traits:
                continue

            new_val = traits[trait] + delta

            # Restrict drift
            baseline = template.get(trait, 0.5)
            if abs(new_val - baseline) > max_drift:
                # Clamp to boundary
                if new_val > baseline:
                    new_val = baseline + max_drift
                else:
                    new_val = baseline - max_drift

            # Clamp to valid range
            new_val = max(0.0, min(1.0, new_val))
            traits[trait] = new_val

        personality["traits"] = traits
        return personality

    # ---------------------------------------
    # CHECK PERMISSIONS
    # ---------------------------------------
    def allow_agent_read_system(self, agent_name: str) -> bool:
        p = self.get_agent_personality(agent_name)
        if not p:
            return False
        return p["permissions"].get("read_system_core", False)

    def allow_agent_read_other_agents(self, agent_name: str) -> bool:
        p = self.get_agent_personality(agent_name)
        if not p:
            return False
        return p["permissions"].get("read_other_agents", False)

    def allow_agent_write_other_agents(self, agent_name: str) -> bool:
        p = self.get_agent_personality(agent_name)
        if not p:
            return False
        return p["permissions"].get("write_other_agents", False)

    def allow_agent_write_system(self, agent_name: str) -> bool:
        p = self.get_agent_personality(agent_name)
        if not p:
            return False
        return p["permissions"].get("write_system_core", False)


# --------------------------------------------------------
# GLOBAL HELPER
# --------------------------------------------------------
personality_manager = PersonalityManager()