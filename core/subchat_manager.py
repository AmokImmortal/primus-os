# /core/subchat_manager.py
# Manages creation, isolation, permissions, security, and state of all sub-chats.

import uuid
from datetime import datetime

from core.subchat_isolation import SubchatIsolationRules
from core.agent_permissions import AgentPermissions
from core.agent_interaction_logger import AgentInteractionLogger
from core.security_enforcer import SecurityEnforcer

class SubchatManager:
    """
    Creates, tracks, isolates, secures, and manages sub-chat instances.
    Acts as the authoritative controller for all branching conversations.
    """

    def __init__(self):
        self.subchats = {}  # subchat_id -> metadata + rules + permissions
        self.logger = AgentInteractionLogger()
        self.security = SecurityEnforcer()

    def create_subchat(self, parent_agent: str, purpose: str, permissions: dict = None):
        """
        Create a new subchat with isolation rules and permissions.
        """
        subchat_id = str(uuid.uuid4())

        isolation = SubchatIsolationRules(
            access_parent_memory=False,
            allow_parent_logs=False,
            parent_context_limit=50
        )

        perms = AgentPermissions(permissions if permissions else {})

        metadata = {
            "id": subchat_id,
            "parent_agent": parent_agent,
            "purpose": purpose,
            "created_at": datetime.utcnow().isoformat(),
            "isolation": isolation,
            "permissions": perms,
            "messages": []
        }

        self.subchats[subchat_id] = metadata

        self.logger.log_event(
            agent=parent_agent,
            action="SUBCHAT_CREATED",
            details={"subchat_id": subchat_id, "purpose": purpose}
        )

        return subchat_id

    def add_message(self, subchat_id: str, sender: str, message: str):
        """
        Add a message to the subchat while enforcing all isolation + security rules.
        """

        if subchat_id not in self.subchats:
            raise ValueError(f"Subchat {subchat_id} does not exist.")

        subchat = self.subchats[subchat_id]

        # Security gate
        if not self.security.allow_message(sender, message, subchat["permissions"]):
            raise PermissionError("Message blocked by security layer.")

        # Isolation enforcement
        sanitized_message = subchat["isolation"].apply_isolation(message)

        subchat["messages"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "sender": sender,
            "content": sanitized_message
        })

        self.logger.log_message(
            agent=sender,
            subchat_id=subchat_id,
            message=sanitized_message
        )

        return True

    def get_messages(self, subchat_id: str):
        """
        Retrieve message history for UI or internal use.
        """
        if subchat_id not in self.subchats:
            raise ValueError(f"Subchat {subchat_id} does not exist.")

        return self.subchats[subchat_id]["messages"]

    def close_subchat(self, subchat_id: str):
        """
        Close and archive the subchat.
        """
        if subchat_id not in self.subchats:
            raise ValueError(f"Subchat {subchat_id} does not exist.")

        subchat = self.subchats[subchat_id]

        self.logger.log_event(
            agent=subchat["parent_agent"],
            action="SUBCHAT_CLOSED",
            details={"subchat_id": subchat_id}
        )

        del self.subchats[subchat_id]
        return True

    def list_subchats(self):
        """
        Return a summary listing of all active subchats.
        """
        return [
            {
                "id": sc["id"],
                "parent_agent": sc["parent_agent"],
                "purpose": sc["purpose"],
                "created_at": sc["created_at"],
            }
            for sc in self.subchats.values()
        ]