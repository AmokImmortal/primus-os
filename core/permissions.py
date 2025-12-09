"""
permissions.py

Central permission and sensitivity helpers for PRIMUS OS.

This module is intentionally self-contained and side-effect free so that:
- PrimusCore, agents, RAG, and network/redaction layers can all share
  the same canonical notion of "who can see what".
- Captain's Log rules stay crystal clear and enforced in code.

Key concepts:

1. Roles (WHO)
   - MASTER_ROOT       : You, inside Captain's Log Master Root Mode.
                         Full, dangerous access to EVERYTHING, including
                         Captain's Log private RAG.
   - MASTER_USER       : You, outside Captain's Log. Very powerful, but
                         MUST NOT see Captain's Log internal data.
   - NORMAL_USER       : A regular interactive user.
   - AGENT             : An internal PRIMUS agent.
   - EXTERNAL_SERVICE  : Any outbound integration (OpenAI, HTTP APIs, etc.).

2. Sensitivity Scopes (WHAT)
   Rough sensitivity buckets used across PRIMUS:

   - SYSTEM_PUBLIC       : Safe for general use and outbound.
   - SYSTEM_PRIVATE      : Personal but not critical; still internal.
   - SYSTEM_SECRET       : Sensitive; internal only. No external services.
   - SYSTEM_TOP_SECRET   : Highly sensitive; heavily restricted.
   - CAPTAINS_LOG_INTERNAL : Special bucket for Captain's Log private RAG.
                             Only MASTER_ROOT sees this.

3. High-level rules (SUMMARY)

   - Captain’s Log data (CAPTAINS_LOG_INTERNAL):
       * ONLY MASTER_ROOT can read/write.
       * MASTER_USER, NORMAL_USER, AGENT, EXTERNAL_SERVICE -> denied.

   - System TOP_SECRET:
       * MASTER_ROOT, MASTER_USER -> allowed.
       * NORMAL_USER, AGENT, EXTERNAL_SERVICE -> denied.

   - System SECRET:
       * MASTER_ROOT, MASTER_USER -> allowed.
       * NORMAL_USER -> can be allowed case-by-case.
       * AGENT, EXTERNAL_SERVICE -> default denied; must be explicitly lifted.

   - System PRIVATE:
       * MASTER_ROOT, MASTER_USER, NORMAL_USER -> allowed.
       * AGENT -> allowed only if explicitly permitted.
       * EXTERNAL_SERVICE -> redacted by default.

   - System PUBLIC:
       * Everyone can read.
       * EXTERNAL_SERVICE is allowed but may still be filtered by redaction.

This file does NOT perform logging or I/O; callers are responsible for
writing to system logs when decisions are made.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterable, Optional


class Role(Enum):
    """Logical actor roles in PRIMUS."""

    MASTER_ROOT = auto()       # Captain's Log Master Root mode
    MASTER_USER = auto()       # You, outside Captain's Log, high privilege
    NORMAL_USER = auto()       # Standard interactive user
    AGENT = auto()             # Internal PRIMUS agent
    EXTERNAL_SERVICE = auto()  # Any outbound integration (APIs, web, etc.)


class Scope(Enum):
    """
    Sensitivity / access scope on data.

    These should be applied at the level of:
      - RAG documents
      - Files
      - Messages
      - Journal entries
    """

    SYSTEM_PUBLIC = auto()
    SYSTEM_PRIVATE = auto()
    SYSTEM_SECRET = auto()
    SYSTEM_TOP_SECRET = auto()
    CAPTAINS_LOG_INTERNAL = auto()


@dataclass(frozen=True)
class PermissionDecision:
    """
    Result of a permission check.

    - allowed: True if access is granted.
    - reason:  Short human-readable explanation.
    - should_redact: If True, caller should strip or mask sensitive parts
                     before sending to EXTERNAL_SERVICE or less-privileged
                     roles.
    """

    allowed: bool
    reason: str
    should_redact: bool = False

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "should_redact": self.should_redact,
        }


# ---------- Scope classification helpers ----------


def classify_scope_from_tags(tags: Optional[Iterable[str]]) -> Scope:
    """
    Map a set of tags/labels onto a Scope.

    Example tags this understands (case-insensitive):
        - "PUBLIC"
        - "PRIVATE"
        - "SECRET"
        - "TOP_SECRET", "TOP-SECRET", "TOP SECRET"
        - "CAPTAINS_LOG", "CAPTAIN", "MASTER_ROOT"

    If no tags are provided, SYSTEM_PRIVATE is used (defensive default).
    """
    if not tags:
        return Scope.SYSTEM_PRIVATE

    normalized = {t.strip().upper() for t in tags if t}

    if any(t in normalized for t in ("CAPTAINS_LOG", "CAPTAIN", "MASTER_ROOT")):
        return Scope.CAPTAINS_LOG_INTERNAL

    if any(t in normalized for t in ("TOP_SECRET", "TOP-SECRET", "TOP SECRET")):
        return Scope.SYSTEM_TOP_SECRET

    if "SECRET" in normalized:
        return Scope.SYSTEM_SECRET

    if "PUBLIC" in normalized:
        return Scope.SYSTEM_PUBLIC

    if "PRIVATE" in normalized:
        return Scope.SYSTEM_PRIVATE

    # Default if tags are unknown but present: treat as PRIVATE
    return Scope.SYSTEM_PRIVATE


# ---------- Core permission logic ----------


def can_read(role: Role, scope: Scope) -> PermissionDecision:
    """
    Decide whether a given role may READ data in the given scope.

    This enforces the high-level security model described in the
    PRIMUS design and Captain's Log specification.
    """

    # Captain's Log internal data is for MASTER_ROOT only.
    if scope is Scope.CAPTAINS_LOG_INTERNAL:
        if role is Role.MASTER_ROOT:
            return PermissionDecision(True, "MASTER_ROOT can read Captain's Log internal data.")
        return PermissionDecision(False, "Captain's Log internal data is only visible to MASTER_ROOT.")

    # Top secret system data: MASTER_ROOT + MASTER_USER only.
    if scope is Scope.SYSTEM_TOP_SECRET:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER):
            return PermissionDecision(True, "High-privilege user may read TOP_SECRET system data.")
        return PermissionDecision(False, "TOP_SECRET system data is restricted to high-privilege users.")

    # Secret system data: MASTER_ROOT + MASTER_USER by default.
    if scope is Scope.SYSTEM_SECRET:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER):
            return PermissionDecision(True, "High-privilege user may read SECRET system data.")
        if role is Role.NORMAL_USER:
            return PermissionDecision(
                False,
                "NORMAL_USER cannot read SECRET system data by default.",
            )
        if role is Role.AGENT:
            return PermissionDecision(
                False,
                "Agents cannot read SECRET system data unless explicitly lifted by higher policy.",
            )
        if role is Role.EXTERNAL_SERVICE:
            return PermissionDecision(
                False,
                "External services cannot receive SECRET system data.",
                should_redact=True,
            )

    # Private system data: internal users OK, agents conditional, external redacted.
    if scope is Scope.SYSTEM_PRIVATE:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER, Role.NORMAL_USER):
            return PermissionDecision(True, "Internal user may read PRIVATE system data.")
        if role is Role.AGENT:
            # Default: deny; PrimusCore or higher policy may override per-agent.
            return PermissionDecision(
                False,
                "Agents require explicit permission to read PRIVATE system data.",
            )
        if role is Role.EXTERNAL_SERVICE:
            return PermissionDecision(
                False,
                "External services should not receive PRIVATE system data.",
                should_redact=True,
            )

    # Public system data: everyone can read, but caller may still redact content.
    if scope is Scope.SYSTEM_PUBLIC:
        if role is Role.EXTERNAL_SERVICE:
            return PermissionDecision(
                True,
                "Public data may be sent to external services.",
                should_redact=False,
            )
        # All internal roles are fine.
        return PermissionDecision(True, "Public system data is readable by all internal roles.")

    # Fallback: extremely defensive.
    return PermissionDecision(
        False,
        "Unknown scope or role; access denied by default.",
        should_redact=True,
    )


def can_write(role: Role, scope: Scope) -> PermissionDecision:
    """
    Decide whether a given role may WRITE/modify data in the given scope.

    Writes are more restricted than reads. In most cases:
      - MASTER_ROOT can write everything.
      - MASTER_USER can write most internal scopes but NOT Captain's Log internals.
      - NORMAL_USER writes to PRIVATE or PUBLIC only.
      - AGENT writes only to its own areas (to be enforced by caller).
      - EXTERNAL_SERVICE never writes directly.
    """

    # Captain's Log internal: MASTER_ROOT only.
    if scope is Scope.CAPTAINS_LOG_INTERNAL:
        if role is Role.MASTER_ROOT:
            return PermissionDecision(True, "MASTER_ROOT may modify Captain's Log internal data.")
        return PermissionDecision(False, "Only MASTER_ROOT may modify Captain's Log internal data.")

    # TOP_SECRET system: MASTER_ROOT and MASTER_USER.
    if scope is Scope.SYSTEM_TOP_SECRET:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER):
            return PermissionDecision(True, "High-privilege user may modify TOP_SECRET system data.")
        return PermissionDecision(False, "TOP_SECRET system data is write-protected for this role.")

    # SECRET system: MASTER_ROOT and MASTER_USER, others denied by default.
    if scope is Scope.SYSTEM_SECRET:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER):
            return PermissionDecision(True, "High-privilege user may modify SECRET system data.")
        return PermissionDecision(False, "SECRET system data is write-protected for this role.")

    # PRIVATE system: internal users and some agents.
    if scope is Scope.SYSTEM_PRIVATE:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER, Role.NORMAL_USER):
            return PermissionDecision(True, "Internal user may modify PRIVATE system data.")
        if role is Role.AGENT:
            # Caller must enforce agent-specific areas; default to deny here.
            return PermissionDecision(
                False,
                "Agents may only write to their own designated areas.",
            )
        if role is Role.EXTERNAL_SERVICE:
            return PermissionDecision(False, "External services cannot modify system data.")

    # PUBLIC system: internal writes allowed; external never writes directly.
    if scope is Scope.SYSTEM_PUBLIC:
        if role in (Role.MASTER_ROOT, Role.MASTER_USER, Role.NORMAL_USER):
            return PermissionDecision(True, "Internal user may modify PUBLIC system data.")
        if role is Role.AGENT:
            # Many agents will be allowed to write content that is PUBLIC.
            return PermissionDecision(True, "Agents may write PUBLIC system data in their own areas.")
        if role is Role.EXTERNAL_SERVICE:
            return PermissionDecision(False, "External services cannot write system data directly.")

    # Fallback.
    return PermissionDecision(False, "Unknown scope or role; writes denied by default.")


# ---------- Redaction helpers for outbound traffic ----------


def should_redact_for_external(scope: Scope) -> bool:
    """
    Convenience helper for outbound integrations.

    Returns True if content in this scope must be redacted or removed
    before sending to EXTERNAL_SERVICE.

    Captain's Log data is ALWAYS treated as non-exportable.
    """
    if scope is Scope.CAPTAINS_LOG_INTERNAL:
        return True
    if scope in (Scope.SYSTEM_TOP_SECRET, Scope.SYSTEM_SECRET, Scope.SYSTEM_PRIVATE):
        return True
    # Public data is allowed to pass; caller may still apply additional filters.
    return False