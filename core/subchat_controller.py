"""
subchat_controller.py
Master orchestrator for the entire Subchat subsystem.

Ties together:
- subchat_state
- subchat_lifecycle
- subchat_events
- subchat_policy
- subchat_security
- subchat_access_control
- subchat_manager
- subchat_router

This controller exposes a clean API for PRIMUS and Agents.
"""

from typing import Optional, Dict, Any

from core.subchat_state import SubchatState
from core.subchat_lifecycle import SubchatLifecycle
from core.subchat_events import SubchatEvents
from core.subchat_policy import SubchatPolicy
from core.subchat_security import SubchatSecurity
from core.subchat_access_control import SubchatAccessControl
from core.subchat_manager import SubchatManager
from core.subchat_router import SubchatRouter


class SubchatController:
    """
    High-level wrapper that unifies all subchat components.
    Everything PRIMUS needs to manage subchats in one place.
    """

    def __init__(self, registry=None, logger=None):
        self.state = SubchatState()
        self.lifecycle = SubchatLifecycle()
        self.events = SubchatEvents()
        self.policy = SubchatPolicy()
        self.security = SubchatSecurity()
        self.access = SubchatAccessControl()
        self.manager = SubchatManager()
        self.router = SubchatRouter()

        self.registry = registry  # agent registry (optional)
        self.logger = logger      # global PRIMUS logger (optional)

    # -------------------------------------------------------------
    # HIGH-LEVEL API
    # -------------------------------------------------------------
    def create_subchat(self, chat_id: str, owner: str, private: bool = False) -> bool:
        """Create a new subchat with required security + lifecycle rules."""
        if self.state.exists(chat_id):
            return False

        # enforce policy
        if not self.policy.allow_create(owner):
            return False

        # create lifecycle entry
        self.lifecycle.initialize(chat_id)

        # create state entry
        self.state.create(chat_id, owner, private)

        # fire event
        self.events.broadcast("subchat_created", {"chat_id": chat_id})

        if self.logger:
            self.logger.info(f"[SubchatController] Subchat created: {chat_id}")

        return True

    def close_subchat(self, chat_id: str, requester: str) -> bool:
        """Close a subchat gracefully."""
        if not self.access.can_close(chat_id, requester):
            return False

        self.lifecycle.terminate(chat_id)
        self.state.delete(chat_id)

        self.events.broadcast("subchat_closed", {"chat_id": chat_id})

        if self.logger:
            self.logger.info(f"[SubchatController] Subchat closed: {chat_id}")

        return True

    def send_message(
        self, chat_id: str, sender: str, message: str
    ) -> Optional[str]:
        """Route a message into the correct subchat with policy + security checks."""

        # existence
        if not self.state.exists(chat_id):
            return None

        # can sender access?
        if not self.access.can_message(chat_id, sender):
            return None

        # sanitize input
        clean_msg = self.security.sanitize(message)

        # enforce policies (no restricted topics, no forbidden cross-talk)
        if not self.policy.validate_message(chat_id, sender, clean_msg):
            return None

        # send it
        routed = self.router.route_message(chat_id, sender, clean_msg)

        # log event
        self.events.broadcast(
            "subchat_message",
            {"chat_id": chat_id, "sender": sender, "msg": clean_msg},
        )

        if self.logger:
            self.logger.info(
                f"[SubchatController] Message routed: {chat_id}::{sender} -> {clean_msg}"
            )

        return routed

    def list_subchats(self) -> Dict[str, Any]:
        """Get list of all existing subchats (non-private only unless Master User)."""
        return self.state.get_all()

    # -------------------------------------------------------------
    # SPECIAL ACCESS ROUTINES
    # -------------------------------------------------------------
    def get_subchat_owner(self, chat_id: str) -> Optional[str]:
        return self.state.get_owner(chat_id)

    def set_subchat_private(self, chat_id: str, requester: str, value: bool) -> bool:
        if not self.access.can_modify(chat_id, requester):
            return False

        self.state.set_private(chat_id, value)
        return True

    def subchat_info(self, chat_id: str) -> Optional[dict]:
        """Return full info about a subchat."""
        return self.state.get(chat_id)


# -------------------------------------------------------------
# FACTORY
# -------------------------------------------------------------
def create_subchat_controller(registry=None, logger=None) -> SubchatController:
    return SubchatController(registry=registry, logger=logger)