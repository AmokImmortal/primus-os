"""Captain's Log Master Root mode manager.

This module wraps the low-level state helpers from ``cl_state`` to provide a
simple, centralized interface for entering, exiting, and inspecting Captain's
Log Master Root Mode (CL-MR). It intentionally does **not** implement
journaling, RAG, encryption, or other Captain's Log features in this phase.
"""

from __future__ import annotations

import logging
from typing import Optional

from System.captains_log import cl_state

logger = logging.getLogger(__name__)


class CaptainsLogManager:
    """High-level manager for Captain's Log Master Root Mode.

    This manager focuses solely on coordinating state transitions and status
    reporting. It does not handle journaling, RAG, encryption, or other
    Captain's Log concerns yet.
    """

    def __init__(self, state: Optional[cl_state.CaptainsLogState] = None) -> None:
        self._state = state or cl_state.get_state()

    def enter(self) -> None:
        """Enter Captain's Log Master Root Mode.

        Delegates to the underlying state helper; journaling and RAG are out of
        scope for this phase.
        """

        logger.info("CaptainsLogManager: enter() requested.")
        cl_state.enter_captains_log_mode()

    def exit(self) -> None:
        """Exit Captain's Log Master Root Mode.

        Delegates to the underlying state helper; journaling and RAG are out of
        scope for this phase.
        """

        logger.info("CaptainsLogManager: exit() requested.")
        cl_state.exit_captains_log_mode()

    def is_active(self) -> bool:
        """Return whether Captain's Log Master Root Mode is active."""

        return cl_state.is_captains_log_mode()

    def get_status(self) -> dict:
        """Return a simple status snapshot for diagnostics.

        The status includes whether CL-MR is active and a textual mode label.
        No journaling or RAG information is included in this phase.
        """

        active = self.is_active()
        return {"active": active, "mode": "captains_log" if active else "normal"}


_manager = CaptainsLogManager()


def get_manager() -> CaptainsLogManager:
    """Return the shared Captain's Log manager instance."""

    return _manager
