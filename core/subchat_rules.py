"""
subchat_rules.py
Defines rule structures, templates, and default enforcement policies for Sub-Chats.
All other Sub-Chat components (validator, security, sandbox, orchestrator) depend on this.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Rule:
    """Defines a single rule and how it should be enforced."""
    id: str
    description: str
    severity: str = "medium"        # low / medium / high / critical
    allowed: bool = True
    conditions: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


@dataclass
class RuleSet:
    """A set of rules applied to a Sub-Chat session."""
    name: str
    rules: Dict[str, Rule] = field(default_factory=dict)
    inherits_from: Optional[str] = None  # allow hierarchical rule inheritance

    def add_rule(self, rule: Rule):
        self.rules[rule.id] = rule

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        return self.rules.get(rule_id)

    def list_rules(self) -> List[Rule]:
        return list(self.rules.values())


class SubchatRules:
    """
    Central authority for all Sub-Chat rule definitions.
    Other modules reference this at runtime for validation and security.
    """

    def __init__(self):
        self.rule_sets: Dict[str, RuleSet] = {}
        self._load_default_rules()

    # -------------------------------------------------------------------------
    # DEFAULT RULE DEFINITIONS
    # -------------------------------------------------------------------------
    def _load_default_rules(self):
        """Load all global, system, agent, and sandbox rule templates."""

        # -------------------------------
        # GLOBAL RULESET
        # -------------------------------
        global_rules = RuleSet(name="global")

        global_rules.add_rule(Rule(
            id="NO_WRITE_OUTSIDE_SANDBOX",
            description="Sub-Chat may not modify files or system state outside its sandbox.",
            severity="critical",
            allowed=False
        ))

        global_rules.add_rule(Rule(
            id="NO_AGENT_OVERRIDE",
            description="Sub-Chats cannot override another agent’s rules, permissions, or identity.",
            severity="critical",
            allowed=False
        ))

        global_rules.add_rule(Rule(
            id="LIMITED_MEMORY_ACCESS",
            description="Sub-Chats can only access memory segments explicitly allowed by parent session.",
            severity="high",
            allowed=True
        ))

        global_rules.add_rule(Rule(
            id="NO_UNAUTHORIZED_PERSONALITY_CHANGES",
            description="Sub-Chats cannot modify PRIMUS personality unless Captain's Log sandbox approves.",
            severity="critical",
            allowed=False
        ))

        self.rule_sets["global"] = global_rules

        # -------------------------------
        # SANDBOX RULESET
        # -------------------------------
        sandbox_rules = RuleSet(name="sandbox", inherits_from="global")

        sandbox_rules.add_rule(Rule(
            id="SANDBOX_MODIFICATIONS_ALLOWED",
            description="System and personality modifications allowed ONLY when approved by user.",
            severity="critical",
            allowed=True,
            conditions={"requires_user_approval": True}
        ))

        sandbox_rules.add_rule(Rule(
            id="NO_INTERNET_ACCESS",
            description="Internet access disabled unless user explicitly toggles override.",
            severity="critical",
            allowed=False
        ))

        sandbox_rules.add_rule(Rule(
            id="FULL_LOG_SUPPRESSION",
            description="No logs are to be written during sandbox mode except user-approved items.",
            severity="high",
            allowed=True,
            metadata={"logging": "disabled"}
        ))

        self.rule_sets["sandbox"] = sandbox_rules

        # -------------------------------
        # AGENT RULESET (template)
        # -------------------------------
        agent_rules = RuleSet(name="agent_default", inherits_from="global")

        agent_rules.add_rule(Rule(
            id="AGENT_READ_ONLY_PARENT_CONTEXT",
            description="Agents can read but not modify parent conversation context.",
            severity="medium",
            allowed=True
        ))

        agent_rules.add_rule(Rule(
            id="AGENT_NO_CROSS_CHAT_LEAK",
            description="Agents may not leak information across sub-chats.",
            severity="critical",
            allowed=False
        ))

        agent_rules.add_rule(Rule(
            id="AGENT_THROTTLE_OUTPUT",
            description="Agent output may be rate-limited to prevent runaway loops.",
            severity="low",
            allowed=True,
            conditions={"max_output_per_second": 5}
        ))

        self.rule_sets["agent_default"] = agent_rules

    # -------------------------------------------------------------------------
    # RULESET ACCESS
    # -------------------------------------------------------------------------
    def get_ruleset(self, name: str) -> Optional[RuleSet]:
        return self.rule_sets.get(name)

    def list_rulesets(self) -> List[str]:
        return list(self.rule_sets.keys())

    # -------------------------------------------------------------------------
    # CUSTOMIZATION
    # -------------------------------------------------------------------------
    def create_custom_ruleset(self, name: str, inherit_from: str = "global") -> RuleSet:
        ruleset = RuleSet(name=name, inherits_from=inherit_from)
        self.rule_sets[name] = ruleset
        return ruleset

    def override_rule(self, ruleset_name: str, rule_id: str, **updates):
        ruleset = self.rule_sets.get(ruleset_name)
        if not ruleset:
            return False

        rule = ruleset.get_rule(rule_id)
        if not rule:
            return False

        for k, v in updates.items():
            setattr(rule, k, v)

        return True


# Singleton accessor
subchat_rules = SubchatRules()