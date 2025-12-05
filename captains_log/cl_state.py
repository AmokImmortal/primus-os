"""Captain's Log Master Root mode state management.

This module provides a lightweight state tracker for Captain's Log Mode.
It intentionally avoids journaling, RAG, redaction, or UI concerns and
serves only to expose a shared state object and helper functions.
"""

from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)


class CaptainsLogState:
    """State container for Captain's Log Master Root Mode."""

    def __init__(self) -> None:
        self.active: bool = False

    def enter(self) -> None:
        """Mark Captain's Log mode as active."""
        self.active = True
        logger.info("Entering Captain's Log Master Root Mode")

    def exit(self) -> None:
        """Mark Captain's Log mode as inactive."""
        self.active = False
        logger.info("Exiting Captain's Log Master Root Mode")

    @property
    def is_active(self) -> bool:
        """Return whether Captain's Log mode is currently active."""
        return self.active


_state = CaptainsLogState()
_state_lock = Lock()


def enter_captains_log_mode() -> CaptainsLogState:
    """Enter Captain's Log Master Root Mode and return the shared state."""
    with _state_lock:
        _state.enter()
        return _state


def exit_captains_log_mode() -> CaptainsLogState:
    """Exit Captain's Log Master Root Mode and return the shared state."""
    with _state_lock:
        _state.exit()
        return _state


def is_captains_log_mode() -> bool:
    """Check whether Captain's Log Master Root Mode is active."""
    with _state_lock:
        return _state.is_active


def get_state() -> CaptainsLogState:
    """Return the shared Captain's Log state instance."""
    return _state
