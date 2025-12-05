# /core/subchat_governor.py
"""
SubChatGovernor
----------------
Highest-level authority for Sub-Chat behavior.

• Enforces ALL policy layers (security, rules, validation).  
• Works with SubChatRules, SubChatValidator, SubChatPolicy, and SubchatSecurity.
• Provides a final YES/NO decision for any Sub-Chat action request.  
• Logs governance decisions for auditing.  
• Ensures sandbox and isolation requirements are met.
"""

from typing import Any, Dict, Optional

from core.subchat_rules import SubChatRules
from core.subchat_validator import SubChatValidator
from core.subchat_security import SubchatSecurity
from core.subchat_policy import SubChatPolicy
from core.subchat_access_control import SubChatAccessControl


class SubChatGovernor:
    def __init__(self):
        self.rules = SubChatRules()
        self.validator = SubChatValidator()
        self.security = SubchatSecurity()
        self.policy = SubChatPolicy()
        self.access = SubChatAccessControl()

    # ------------------------------------------
    # MASTER DECISION ENGINE
    # ------------------------------------------
    def authorize_action(
        self,
        subchat_id: str,
        user_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Final authority. Determines if a sub-chat action may proceed.
        """

        # 1. Security Check (credentials, tamper prevention, isolation)
        if not self.security.verify_action(subchat_id, user_id, action_type, payload):
            self._log_decision(subchat_id, action_type, "DENIED: security")
            return False

        # 2. Access Control Check (permissions)
        if not self.access.has_permission(subchat_id, user_id, action_type):
            self._log_decision(subchat_id, action_type, "DENIED: access")
            return False

        # 3. Validation Check (input structure, content validity)
        if not self.validator.validate_request(action_type, payload):
            self._log_decision(subchat_id, action_type, "DENIED: validation")
            return False

        # 4. Policy Enforcement (sandbox rules, agent communication limits)
        if not self.policy.enforce(subchat_id, action_type, payload):
            self._log_decision(subchat_id, action_type, "DENIED: policy")
            return False

        # 5. Ruleset Enforcement (rate limits, behavior restrictions)
        if not self.rules.check_rules(subchat_id, action_type):
            self._log_decision(subchat_id, action_type, "DENIED: rules")
            return False

        # If all checks pass → APPROVED
        self._log_decision(subchat_id, action_type, "APPROVED")
        return True

    # ------------------------------------------
    # INTERNAL GOVERNANCE LOGGING
    # ------------------------------------------
    def _log_decision(self, subchat_id: str, action: str, verdict: str):
        """Record governor decisions for diagnostics or audits."""
        print(f"[SubChatGovernor] SubChat={subchat_id} | Action={action} | Result={verdict}")

    # ------------------------------------------
    # OVERRIDE SWITCHES (Root-Level, Future Captain's Log Use)
    # ------------------------------------------
    def manual_override(self, action: str, allow: bool, reason: str = ""):
        """
        Used ONLY in Captain’s Log Sandbox Mode.
        Allows you to force-approve or force-deny actions.
        """
        print(f"[SubChatGovernor:OVERRIDE] Action={action} | ForceAllow={allow} | Reason={reason}")
        return allow