# /core/subchat_normalizer.py
# Normalizes and standardizes SubChat text input/output.
# Ensures consistent formatting, punctuation, spacing, casing (when allowed),
# and strips any dangerous or system-breaking characters.

import re
import unicodedata

class SubChatNormalizer:
    def __init__(self):
        # Define normalization rules
        self.max_length = 12000  # safety cutoff for runaway messages
        self.allow_unicode = True  # can be changed later in configs

    def normalize(self, text: str) -> str:
        """Main normalization pipeline."""
        if not isinstance(text, str):
            return ""

        text = self._strip_invalid_chars(text)
        text = self._normalize_unicode(text)
        text = self._standardize_whitespace(text)
        text = self._sanitize_control_characters(text)
        text = self._limit_length(text)

        return text.strip()

    def _strip_invalid_chars(self, text: str) -> str:
        """Remove characters that should never appear in SubChats."""
        # Remove null bytes, terminal control escape sequences, etc.
        return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    def _normalize_unicode(self, text: str) -> str:
        """Normalize unicode so all text is consistent."""
        if self.allow_unicode:
            return unicodedata.normalize("NFC", text)
        else:
            # remove all non-ascii chars
            return text.encode("ascii", "ignore").decode()

    def _standardize_whitespace(self, text: str) -> str:
        """Ensure whitespace is clean and predictable."""
        text = re.sub(r"\s+", " ", text)  # collapse multiple spaces
        text = re.sub(r" ?\n ?", "\n", text)  # clean up newlines
        return text

    def _sanitize_control_characters(self, text: str) -> str:
        """Remove hidden or control characters that may disrupt logs."""
        return "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")

    def _limit_length(self, text: str) -> str:
        """Ensure message length cannot exceed safe bounds."""
        if len(text) > self.max_length:
            return text[:self.max_length] + "…"
        return text