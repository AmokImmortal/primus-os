# /core/subchat_sanitizer.py
# PRIMUS OS — SubChat Sanitizer
# Ensures all incoming/outgoing SubChat data is safe, normalized, and non-corrupt.

import re
import json
from typing import Any, Dict


class SubChatSanitizer:
    """
    Cleans, validates, and scrubs unsafe or malformed content before it enters
    the SubChat engine, memory system, or persistence layers.
    """

    SAFE_CHAR_PATTERN = re.compile(r"[^a-zA-Z0-9 .,!?@#%&()_\-+=/\[\]{}:;\'\"]+")

    def sanitize_text(self, text: str) -> str:
        """
        Remove unsafe characters, normalize whitespace, and ensure safe output.
        """
        if not isinstance(text, str):
            return ""

        cleaned = self.SAFE_CHAR_PATTERN.sub("", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize all dict values.
        """
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned[key] = self.sanitize_text(value)
            elif isinstance(value, dict):
                cleaned[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                cleaned[key] = self.sanitize_list(value)
            else:
                cleaned[key] = value
        return cleaned

    def sanitize_list(self, data: list) -> list:
        """
        Recursively sanitize all list values.
        """
        cleaned = []
        for item in data:
            if isinstance(item, str):
                cleaned.append(self.sanitize_text