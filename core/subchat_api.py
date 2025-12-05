import uuid
from typing import Optional, List, Dict, Any

from core.subchat_manager import SubchatManager
from core.subchat_router import SubchatRouter
from core.subchat_security import SubchatSecurity
from core.subchat_access_control import SubchatAccessControl
from core.subchat_policy import SubchatPolicy
from core.subchat_state import SubchatState
from core.subchat_lifecycle import SubchatLifecycle
from core.subchat_events import SubchatEvents


class SubchatAPI:
    """
    High-level API for interacting with the Subchat System.
    Used by:
      - PRIMUS
      - Specialized Agents
      - Session Manager
      - Internal Core Systems
    """

    def __init__(self):
        self.manager = SubchatManager()
        self.router = SubchatRouter()
        self.security = SubchatSecurity()
        self.access = SubchatAccessControl()
        self.policy = SubchatPolicy()
        self.state = SubchatState()
        self.lifecycle = SubchatLifecycle()
        self.events = SubchatEvents()

    # -------------------------------------------------------------
    # CREATE SUBCHAT
    # -------------------------------------------------------------
    def create_subchat(
        self,
        owner_id: str,
        label: str,
        private: bool = False,
        password: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Creates a new subchat container.
        """

        # Security validation
        if private and not password:
            raise ValueError("Private subchats must include a password.")

        subchat_id = str(uuid.uuid4())

        # Lifecycle event: before creation
        self.events.before_create(subchat_id, owner_id, label)

        self.manager.create_subchat(
            subchat_id=subchat_id,
            owner_id=owner_id,
            label=label,
            private=private,
            password=password,
            metadata=metadata or {}
        )

        # Policy application
        self.policy.apply_creation_policy(subchat_id, owner_id)

        # Lifecycle event: after creation
        self.events.after_create(subchat_id, owner_id, label)

        return subchat_id

    # -------------------------------------------------------------
    # SEND MESSAGE
    # -------------------------------------------------------------
    def send_message(
        self,
        subchat_id: str,
        sender_id: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Sends a message into a subchat.
        """

        # Security validation
        self.security.validate_message(subchat_id, sender_id, message)

        # Access control enforcement
        self.access.validate_send(subchat_id, sender_id)

        # Policy application
        self.policy.enforce_message_policy(subchat_id, sender_id, message)

        # Deliver message through router
        delivery_result = self.router.deliver_message(
            subchat_id=subchat_id,
            sender_id=sender_id,
            message=message
        )

        # Event trigger
        self.events.on_message(subchat_id, sender_id, message)

        return delivery_result

    # -------------------------------------------------------------
    # READ SUBCHAT HISTORY
    # -------------------------------------------------------------
    def read_history(
        self,
        subchat_id: str,
        requester_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Returns recent messages.
        """

        self.access.validate_read(subchat_id, requester_id)

        return self.manager.get_history(subchat_id, limit=limit)

    # -------------------------------------------------------------
    # SET PASSWORD
    # -------------------------------------------------------------
    def set_password(
        self,
        subchat_id: str,
        requester_id: str,
        new_password: str
    ):
        """
        Sets or updates a subchat's password.
        """

        self.access.validate_owner(subchat_id, requester_id)

        self.manager.update_password(subchat_id, new_password)

        self.events.on_password_change(subchat_id, requester_id)

    # -------------------------------------------------------------
    # CLOSE SUBCHAT
    # -------------------------------------------------------------
    def close_subchat(self, subchat_id: str, requester_id: str):
        """
        Closes a subchat and archives it.
        """

        self.access.validate_owner(subchat_id, requester_id)
        self.lifecycle.close_subchat(subchat_id)
        self.events.on_close(subchat_id, requester_id)

    # -------------------------------------------------------------
    # FORCE RESET (Admin Only)
    # -------------------------------------------------------------
    def force_reset_subchat(self, subchat_id: str):
        """
        Emergency cleanup and reset.
        """

        self.lifecycle.force_reset(subchat_id)
        self.state.reset_state(subchat_id)
        self.events.on_force_reset(subchat_id)


# Export instance for global use
subchat_api = SubchatAPI()