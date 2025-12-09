"""
security_gate.py

Central runtime toggle for:
- PRIMUS operating mode (normal / master_user / captains_log).
- External network access (on/off).
- Outbound redaction decisions using permissions.py.

This module is intentionally small and stateful. It is the "live switchboard"
that PrimusRuntime, Captain's Log, agents, and outbound connectors consult
to decide:

- What mode PRIMUS is currently in.
- Whether any external HTTP/API calls are allowed at all.
- Whether data in a given sensitivity scope must be redacted before sending.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .permissions import Role, Scope, should_redact_for_external, PermissionDecision


class PrimusMode(Enum):
    """
    High-level PRIMUS operating modes.

    - NORMAL       : Default runtime mode.
    - MASTER_USER  : You, with elevated authority, outside Captain's Log.
    - CAPTAINS_LOG : Captain's Log Master Root mode (MASTER_ROOT role).
    """

    NORMAL = auto()
    MASTER_USER = auto()
    CAPTAINS_LOG = auto()


@dataclass
class SecurityGateState:
    """
    In-memory state for the SecurityGate singleton.

    This keeps:
    - Current high-level PRIMUS mode.
    - Whether external network access is allowed at all.
    """

    mode: PrimusMode = PrimusMode.NORMAL
    external_network_allowed: bool = False


class SecurityGate:
    """
    SecurityGate controls live mode and external access decisions.

    It does NOT talk to the network or log anything itself; callers
    (PrimusRuntime, PrimusCore, connectors) are responsible for I/O
    and logging when they obey or override these decisions.
    """

    def __init__(self) -> None:
        self._state = SecurityGateState()

    # -------------------------------------------------
    # Mode control
    # -------------------------------------------------
    def set_mode(self, mode: PrimusMode) -> None:
        """
        Set the current PRIMUS mode.
        """
        self._state.mode = mode

    def get_mode(self) -> PrimusMode:
        return self._state.mode

    def is_captains_log_active(self) -> bool:
        """
        True if PRIMUS is currently in Captain's Log Master Root mode.
        """
        return self._state.mode is PrimusMode.CAPTAINS_LOG

    # -------------------------------------------------
    # External network toggle
    # -------------------------------------------------
    def allow_external_network(self, allowed: bool) -> None:
        """
        Toggle whether any external HTTP/API calls are permitted.
        This is a master kill-switch for outbound network use.
        """
        self._state.external_network_allowed = bool(allowed)

    def is_external_network_allowed(self) -> bool:
        return self._state.external_network_allowed

    # -------------------------------------------------
    # Role derivation from mode
    # -------------------------------------------------
    def current_role_for_user(self) -> Role:
        """
        Map the current mode to a logical Role for permission checks.
        This is primarily used when deciding what YOU (the local user)
        are allowed to see or modify in a given mode.
        """
        if self._state.mode is PrimusMode.CAPTAINS_LOG:
            return Role.MASTER_ROOT
        if self._state.mode is PrimusMode.MASTER_USER:
            return Role.MASTER_USER
        return Role.NORMAL_USER

    # -------------------------------------------------
    # Outbound checks
    # -------------------------------------------------
    def evaluate_outbound(
        self,
        scope: Scope,
        role: Role = Role.EXTERNAL_SERVICE,
    ) -> PermissionDecision:
        """
        Decide whether it is permissible to send data in 'scope'
        to an external integration representing 'role'.

        Typical use:
            - role = EXTERNAL_SERVICE for HTTP / OpenAI / etc.
            - scope derived from tags on the document/message.

        This consults:
            - external_network_allowed (kill switch)
            - should_redact_for_external(scope)
        """
        if not self._state.external_network_allowed:
            return PermissionDecision(
                allowed=False,
                reason="External network access is currently disabled.",
                should_redact=True,
            )

        # For external services, we treat all scopes conservatively.
        if role is Role.EXTERNAL_SERVICE:
            if should_redact_for_external(scope):
                return PermissionDecision(
                    allowed=False,
                    reason="Data scope is not safe for external services; redaction required.",
                    should_redact=True,
                )
            return PermissionDecision(
                allowed=True,
                reason="Data scope is PUBLIC; external transmission allowed.",
                should_redact=False,
            )

        # For non-external roles, caller should use permissions.can_read/write directly.
        # Here we default to a permissive stance, as this is "outbound" oriented.
        return PermissionDecision(
            allowed=True,
            reason="Non-external role; outbound evaluation not restrictive.",
            should_redact=False,
        )

    # -------------------------------------------------
    # Status reporting (for bootup tests / diagnostics)
    # -------------------------------------------------
    def get_status(self) -> dict:
        """
        Lightweight status dict suitable for bootup tests and
        diagnostic logging. Contains no sensitive data.
        """
        return {
            "mode": self._state.mode.name.lower(),
            "captains_log_active": self.is_captains_log_active(),
            "external_network_allowed": self._state.external_network_allowed,
        }


# Singleton instance
_gate: Optional[SecurityGate] = None


def get_security_gate() -> SecurityGate:
    global _gate
    if _gate is None:
        _gate = SecurityGate()
    return _gate
