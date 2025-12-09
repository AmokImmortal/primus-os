"""Security Gate subsystem for PRIMUS OS boot-time introspection.

This lightweight module reports simple permission guidance based on Captain's
Log Master Root mode status. It does **not** enforce real restrictions or
perform any I/O. Instead, it offers a minimal foundation that higher-level
runtime and boot-test components can query during initialization.
"""

from __future__ import annotations

import logging
from typing import Optional

from captains_log.cl_manager import CaptainsLogManager, get_manager

logger = logging.getLogger(__name__)


class SecurityGate:
    """Foundation layer for PRIMUS OS security gating.

    The gate surfaces basic permission guidance derived from Captain's Log
    Master Root mode state. Enforcement of networking, journaling, or other
    policies is intentionally deferred to higher layers.
    """

    def __init__(self, manager: Optional[CaptainsLogManager] = None) -> None:
        self._manager = manager or get_manager()

    def is_captains_log_active(self) -> bool:
        """Return whether Captain's Log Master Root mode is active."""

        return self._manager.is_active()

    def external_network_allowed(self) -> bool:
        """Report whether external network access should be considered allowed.

        Network access is treated as disallowed when Captain's Log mode is
        active and allowed otherwise. This method does not perform or trigger
        any network actions.
        """

        return not self.is_captains_log_active()

    def get_status(self) -> dict:
        """Return a status snapshot for boot-time diagnostics.

        The status describes Captain's Log mode activity and whether external
        network access is presently considered permissible. This is intended for
        runtime introspection, not enforcement.
        """

        active = self.is_captains_log_active()
        status = {
            "captains_log_active": active,
            "external_network_allowed": not active,
            "mode": "captains_log" if active else "normal",
        }
        logger.debug("SecurityGate status generated: %s", status)
        return status


_security_gate = SecurityGate()


def get_security_gate() -> SecurityGate:
    """Return the shared SecurityGate instance."""

    return _security_gate
