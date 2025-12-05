# /core/subchat_filters.py

class SubChatFilterEngine:
    """
    Handles content filtering for SubChats.
    Includes: safety filters, profanity filters, pattern-based filters,
    allow/deny lists, and sanitization routing.
    """

    def __init__(self):
        self.profanity_list = set()
        self.block_patterns = []
        self.allow_patterns = []
        self.custom_rules = []

    def load_default_filters(self):
        self.profanity_list.update({
            "badword1", "badword2", "badword3"
        })

    def add_profanity(self, word: str):
        self.profanity_list.add(word.lower())

    def remove_profanity(self, word: str):
        self.profanity_list.discard(word.lower())

    def register_block_pattern(self, pattern_callable):
        """pattern_callable must accept (text) and return True if blocked."""
        self.block_patterns.append(pattern_callable)

    def register_allow_pattern(self, pattern_callable):
        """pattern_callable returns True if content should bypass blocks."""
        self.allow_patterns.append(pattern_callable)

    def register_custom_rule(self, rule_callable):
        """rule_callable(text) → dict {allowed: bool, reason: str}"""
        self.custom_rules.append(rule_callable)

    def check_profanity(self, text: str) -> bool:
        lowered = text.lower()
        return any(word in lowered for word in self.profanity_list)

    def run_block_patterns(self, text: str) -> bool:
        return any(pattern(text) for pattern in self.block_patterns)

    def run_allow_patterns(self, text: str) -> bool:
        return any(pattern(text) for pattern in self.allow_patterns)

    def run_custom_rules(self, text: str):
        results = []
        for rule in self.custom_rules:
            try:
                result = rule(text)
                if isinstance(result, dict):
                    results.append(result)
            except Exception as e:
                results.append({
                    "allowed": False,
                    "reason": f"Rule error: {str(e)}"
                })
        return results

    def evaluate(self, text: str) -> dict:
        if self.run_allow_patterns(text):
            return {"allowed": True, "reason": "Allow pattern matched"}

        if self.check_profanity(text):
            return {"allowed": False, "reason": "Profanity detected"}

        if self.run_block_patterns(text):
            return {"allowed": False, "reason": "Block pattern triggered"}

        custom_results = self.run_custom_rules(text)
        for res in custom_results:
            if not res.get("allowed", True):
                return res

        return {"allowed": True, "reason": "Passed all filters"}