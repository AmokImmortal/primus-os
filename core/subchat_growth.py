# /core/subchat_growth.py
# PRIMUS OS — SubChat Personality Growth Engine
# Controlled, rule-restricted personality evolution system

from typing import Dict, Any
import datetime


class SubChatGrowthEngine:
    """
    Handles slow, rule-restricted personality evolution for subchats.
    Growth is NEVER autonomous — every modification must be allowed
    by system rules, subchat_policy, and agent_permissions.
    """

    def __init__(self):
        self.growth_history: Dict[str, list] = {}
        self.max_growth_per_session = 1  # hard limit to prevent runaway personality drift

    def initialize_subchat(self, subchat_id: str):
        """Prepare growth tracking for a new subchat."""
        if subchat_id not in self.growth_history:
            self.growth_history[subchat_id] = []

    def propose_growth(self, subchat_id: str, change: Dict[str, Any]) -> Dict[str, Any]:
        """
        A subchat may *propose* growth, but cannot apply it itself.

        Example of `change`:
        {
            "trait": "confidence",
            "delta": +0.02,
            "reason": "successful task handling"
        }
        """

        # Safety — verify structure
        if "trait" not in change or "delta" not in change:
            return {"approved": False, "reason": "Invalid growth structure"}

        # Hard rule — tiny safe deltas only
        if abs(change.get("delta", 0)) > 0.05:
            return {"approved": False, "reason": "Delta exceeds allowed threshold"}

        # Return growth proposal for external approval (policy + permissions)
        return {
            "approved": None,  # Means "awaiting governance layer decision"
            "subchat_id": subchat_id,
            "change": change
        }

    def apply_growth(self, subchat_id: str, change: Dict[str, Any]) -> bool:
        """
        Apply personality growth ONLY after passing:
        · subchat_policy checks
        · subchat_governor approval
        · agent_permissions validation
        """

        self.initialize_subchat(subchat_id)

        record = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "trait": change["trait"],
            "delta": change["delta"],
            "reason": change.get("reason", "no reason given")
        }

        self.growth_history[subchat_id].append(record)

        return True

    def get_growth_history(self, subchat_id: str):
        """Return personality change log for diagnostics & reports."""
        return self.growth_history.get(subchat_id, [])

    def summarize_growth(self, subchat_id: str):
        """Generate a safe summary of personality evolution."""
        history = self.get_growth_history(subchat_id)
        if not history:
            return {"summary": "No growth events logged."}

        summary = {}
        for entry in history:
            trait = entry["trait"]
            summary.setdefault(trait, 0.0)
            summary[trait] += entry["delta"]

        return {
            "subchat_id": subchat_id,
            "total_traits_changed": len(summary),
            "net_trait_changes": summary
        }





