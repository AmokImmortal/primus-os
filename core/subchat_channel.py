# ============================================================
# File: /core/subchat_channel.py
# Description:
#   Defines message channels used by the SubChat system.
#   Channels represent communication paths between:
#       - SubChats
#       - Parent chats
#       - Agents
#       - System-level events
#
#   Used by:
#       subchat_router_core
#       subchat_gateway
#       subchat_service
#       subchat_event_bus
# ============================================================

class SubChatChannel:
    """Represents a communication channel within the SubChat system."""

    def __init__(self, name: str, channel_type: str = "direct"):
        """
        Args:
            name (str): Unique channel name.
            channel_type (str): Type of channel:
                - "direct"        (one-to-one)
                - "broadcast"     (one-to-many)
                - "system"        (restricted, system-only)
        """
        self.name = name
        self.channel_type = channel_type
        self.subscribers = set()

    # --------------------------------------------------------
    # CHANNEL SUBSCRIPTION HANDLING
    # --------------------------------------------------------

    def subscribe(self, subchat_id: str):
        """Registers a SubChat to listen to this channel."""
        self.subscribers.add(subchat_id)

    def unsubscribe(self, subchat_id: str):
        """Removes a SubChat from this channel."""
        if subchat_id in self.subscribers:
            self.subscribers.remove(subchat_id)

    def list_subscribers(self):
        """Returns a list of all subscribers listening on this channel."""
        return list(self.subscribers)

    # --------------------------------------------------------
    # MESSAGE DISPATCH
    # --------------------------------------------------------

    def dispatch(self, message: dict) -> dict:
        """
        Dispatches a message depending on channel type.

        Returns:
            dict: routing metadata
        """

        if self.channel_type == "direct":
            return {
                "status": "ok",
                "mode": "direct",
                "targets": list(self.subscribers)[:1]  # first subscriber only
            }

        elif self.channel_type == "broadcast":
            return {
                "status": "ok",
                "mode": "broadcast",
                "targets": list(self.subscribers)
            }

        elif self.channel_type == "system":
            return {
                "status": "ok",
                "mode": "system",
                "targets": list(self.subscribers)
            }

        return {
            "status": "error",
            "mode": "unknown",
            "targets": []
        }