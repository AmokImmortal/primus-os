# /core/subchat_renderer.py

class SubChatRenderer:
    """
    Converts processed SubChat messages into UI-ready render data.
    Handles layout shaping, metadata injection, color themes,
    sender formatting, timestamp formatting, and message grouping.
    """

    def __init__(self):
        self.themes = {
            "default": {
                "user_color": "#4A90E2",
                "agent_color": "#7B61FF",
                "system_color": "#B0B0B0",
                "error_color": "#FF4D4D",
            }
        }
        self.active_theme = "default"

    def set_theme(self, theme_name: str):
        if theme_name in self.themes:
            self.active_theme = theme_name

    def render(self, message: dict) -> dict:
        """
        Convert a normalized message into a UI-friendly render object.

        Expected message format before rendering:
        {
            "sender": "user" | "agent" | "system",
            "text": "string",
            "timestamp": "ISO-8601 str",
            "channel": "subchat_id",
            "error": False
        }
        """
        theme = self.themes[self.active_theme]
        sender = message.get("sender", "system")

        color = (
            theme["error_color"] if message.get("error") else
            theme.get(f"{sender}_color", theme["system_color"])
        )

        return {
            "text": message.get("text", ""),
            "timestamp": message.get("timestamp", ""),
            "sender": sender,
            "color": color,
            "channel": message.get("channel", "unknown"),
            "group_key": self._group_key(sender, message.get("timestamp"))
        }

    def batch_render(self, messages: list) -> list:
        """
        Render a list of normalized messages.
        """
        return [self.render(m) for m in messages]

    def _group_key(self, sender: str, timestamp: str) -> str:
        """
        Group messages visually (e.g., consecutive messages from same sender).
        """
        return f"{sender}-{timestamp[:10]}"  # group by date + sender