# /core/subchat_formatter.py
# Handles final formatting, styling, timestamps, and display prep for SubChat messages.

import datetime
from typing import Dict, Any


class SubChatFormatter:
    """
    Formats SubChat messages for clean display and logging.
    Normalizes timestamps, adds speaker labels, and ensures consistent structure.
    """

    def __init__(self):
        pass

    def timestamp(self) -> str:
        """Return an ISO8601 timestamp for message records."""
        return datetime.datetime.utcnow().isoformat()

    def format_message(self, agent: str, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Returns a fully formatted message dictionary:
            - agent: name of the speaker
            - timestamp: generated timestamp
            - content: cleaned text
            - metadata: optional additional fields (sanitized)
        """
        return {
            "agent": agent,
            "timestamp": self.timestamp(),
            "content": self.clean_whitespace(content),
            "metadata": metadata or {}
        }

    def clean_whitespace(self, text: str) -> str:
        """Removes excessive whitespace and ensures clean formatting."""
        return " ".join(text.split())

    def pretty_print(self, message: Dict[str, Any]) -> str:
        """
        Creates a human-readable formatted string.
        Useful for UI preview or CLI debug display.
        """
        agent = message.get("agent", "Unknown")
        ts = message.get("timestamp", "Unknown Time")
        content = message.get("content", "")

        return f"[{ts}] {agent}: {content}"

    def apply_style(self, message: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies styling rules (colors, prefixes, etc.)
        This does NOT render UI — just annotates message structure
        for UI to interpret.
        """
        formatted = message.copy()
        formatted["style"] = style
        return formatted