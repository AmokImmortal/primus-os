# /core/subchat_interface.py
# Provides a safe, unified public interface for all SubChat operations.
# All internal modules route through here to ensure centralized policy enforcement.

from typing import Optional, List, Dict, Any
from .subchat_manager import SubChatManager
from .subchat_policy import SubChatPolicy
from .subchat_access_control import SubChatAccessControl
from .subchat_state import SubChatState
from .subchat_events import SubChatEventBus
from .subchat_runtime import SubChatRuntime
from .subchat_personality import SubChatPersonalityEngine
from .subchat_memory import SubChatMemoryEngine
from .subchat_storage import SubChatStorage
from .subchat_sanitizer import SubChatSanitizer
from .subchat_filters import SubChatFilters
from .subchat_normalizer import SubChatNormalizer
from .subchat_formatter import SubChatFormatter

class SubChatInterface:
    def __init__(self):
        self.manager = SubChatManager()
        self.policy = SubChatPolicy()
        self.access = SubChatAccessControl()
        self.state = SubChatState()
        self.events = SubChatEventBus()
        self.runtime = SubChatRuntime()
        self.personality = SubChatPersonalityEngine()
        self.memory = SubChatMemoryEngine()
        self.storage = SubChatStorage()

        # Preprocessing layers
        self.sanitizer = SubChatSanitizer()
        self.filters = SubChatFilters()
        self.normalizer = SubChatNormalizer()
        self.formatter = SubChatFormatter()

    # ----------------------------------------------------------------------
    # PUBLIC SAFE INTERFACE LAYER
    # ----------------------------------------------------------------------

    def create_subchat(self, owner: str, base_personality: dict, is_private: bool = False) -> str:
        """Creates a new subchat with required metadata and restrictions."""
        self.policy.validate_creation(owner)
        subchat_id = self.manager.create_new(owner, is_private=is_private)
        self.personality.initialize_personality(subchat_id, base_personality)
        self.memory.init_memory(subchat_id)
        self.storage.init_storage(subchat_id)
        self.state.set_active(subchat_id, True)
        self.events.emit("subchat_created", {"id": subchat_id, "owner": owner})
        return subchat_id

    def post_message(
        self, subchat_id: str, sender: str, message: str
    ) -> Optional[str]:
        """Posts a sanitized, filtered message into the subchat runtime."""
        if not self.access.can_post(sender, subchat_id):
            raise PermissionError("Sender not allowed to post to this subchat")

        message = self.sanitizer.clean(message)
        message = self.filters.apply(message)
        message = self.normalizer.normalize(message)

        reply = self.runtime.process_message(subchat_id, sender, message)

        formatted = self.formatter.format(reply)
        self.events.emit("message_posted", {"subchat_id": subchat_id, "sender": sender})
        return formatted

    def get_history(self, subchat_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves part of the subchat history safely."""
        self.policy.validate_read(subchat_id)
        return self.storage.load_history(subchat_id, limit=limit)

    def get_state(self, subchat_id: str) -> Dict[str, Any]:
        """Returns safe, filtered state data."""
        return self.state.get_state(subchat_id)

    def close_subchat(self, subchat_id: str, requester: str) -> bool:
        """Closes a subchat while enforcing policy restrictions."""
        self.policy.validate_close(requester, subchat_id)
        self.state.set_active(subchat_id, False)
        self.events.emit("subchat_closed", {"id": subchat_id, "by": requester})
        return True

    def delete_subchat(self, subchat_id: str, requester: str) -> bool:
        """Fully deletes a subchat."""
        self.policy.validate_delete(requester, subchat_id)
        self.manager.delete(subchat_id)
        self.events.emit("subchat_deleted", {"id": subchat_id, "by": requester})
        return True

    # ----------------------------------------------------------------------
    # HIGH-LEVEL UTILITY FUNCTIONS
    # ----------------------------------------------------------------------

    def list_subchats_for(self, user: str) -> List[str]:
        return self.manager.list_for(user)

    def summarize(self, subchat_id: str) -> str:
        """Short summary of subchat memory and state."""
        history = self.storage.load_history(subchat_id, limit=200)
        return self.runtime.generate_summary(subchat_id, history)

    def get_personality(self, subchat_id: str) -> dict:
        return self.personality.get_personality(subchat_id)

    def update_personality(self, subchat_id: str, requester: str, updates: dict):
        self.policy.validate_personality_update(requester, subchat_id)
        self.personality.update_personality(subchat_id, updates)
        return True