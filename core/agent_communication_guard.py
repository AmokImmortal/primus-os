"""
agent_communication_guard.py
--------------------------------
PRIMUS OS – Agent Communication Firewall

Purpose:
    Prevent any agent → agent communication unless:
        • The attempt is explicitly allowed in security_enforcer
        • The user grants permission (for temporary or permanent approval)
        • The communication trail is logged (but ONLY outside Captain's Log Sandbox)
"""

from typing import Dict, Optional
from core.security_enforcer import SecurityEnforcer


class AgentCommunicationGuard:
    def __init__(self):
        self.enforcer = SecurityEnforcer()

        # A temporary approval table (auto-clears after use)
        self.temp_approvals: Dict[str, bool] = {}

        # Persistent allowlist for agent pairs (user must authorize)
        self.agent_allowlist: Dict[str, bool] = {}

    def _key(self, sender: str, receiver: str) -> str:
        """Internal key format for indexing pair permissions."""
        return f"{sender}->{receiver}"

    def request_temp_approval(self, sender: str, receiver: str):
        """
        Called when an agent attempts to message another agent.
        SecurityEnforcer decides whether to prompt the user.
        """
        key = self._key(sender, receiver)

        if self.enforcer.require_user_approval(
            action_type="agent_to_agent",
            details={"sender": sender, "receiver": receiver}
        ):
            # Temp approval is granted explicitly by user
            self.temp_approvals[key] = True
            return True

        return False

    def permanently_allow(self, sender: str, receiver: str):
        """
        Allows future communications between the pair without prompts.
        Only executed after explicit user permission.
        """
        key = self._key(sender, receiver)
        self.agent_allowlist[key] = True

    def revoke_permission(self, sender: str, receiver: str):
        """
        Removes allowlist entry (used by the user at any time).
        """
        key = self._key(sender, receiver)
        if key in self.agent_allowlist:
            del self.agent_allowlist[key]
        if key in self.temp_approvals:
            del self.temp_approvals[key]

    def can_communicate(self, sender: str, receiver: str) -> bool:
        """
        Main gatekeeper.
        Determines if agent → agent communication is allowed.
        """
        key = self._key(sender, receiver)

        # 1 — permanent allowlist
        if key in self.agent_allowlist:
            return True

        # 2 — temp one-time approval
        if self.temp_approvals.get(key, False):
            del self.temp_approvals[key]  # consume approval
            return True

        # 3 — no approval exists → must request it
        return False

    def enforce(self, sender: str, receiver: str) -> bool:
        """
        Called before ANY agent tries to send a message to another agent.
        """
        if self.can_communicate(sender, receiver):
            return True

        return self.request_temp_approval(sender, receiver)





