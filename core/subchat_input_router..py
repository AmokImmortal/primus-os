# /core/subchat_input_router.py
# Routes raw user input through the SubChat input pipeline:
# formatter → normalizer → filters → sanitizer → runtime engine

from core.subchat_formatter import SubChatFormatter
from core.subchat_normalizer import SubChatNormalizer
from core.subchat_filters import SubChatFilterEngine
from core.subchat_sanitizer import SubChatSanitizer


class SubChatInputRouter:
    def __init__(self):
        self.formatter = SubChatFormatter()
        self.normalizer = SubChatNormalizer()
        self.filter_engine = SubChatFilterEngine()
        self.sanitizer = SubChatSanitizer()

    def route(self, raw_text: str, subchat_id: str) -> str:
        """Full input pipeline for SubChats."""

        # Step 1: Formatting
        formatted = self.formatter.format(raw_text, subchat_id=subchat_id)

        # Step 2: Normalization
        normalized = self.normalizer.normalize(formatted)

        # Step 3: Filtering
        filtered = self.filter_engine.apply_filters(normalized)

        # Step 4: Sanitization
        cleaned = self.sanitizer.sanitize(filtered)

        return cleaned