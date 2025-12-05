"""Captain's Log Master Root mode manager (framework only).

This module provides a minimal, import-safe Captain's Log manager that wraps the
shared state object exposed by ``cl_state``. It intentionally avoids
implementing journaling, RAG, encryption, or any file I/O in this phase. The
purpose is to offer a stable API for the runtime and future subsystems while
remaining side-effect free.
"""

from __future__ import annotations

from typing import Dict, Optional

from System.captains_log import cl_state


class CaptainsLogManager:
    """High-level manager for Captain's Log Master Root Mode.

    The manager exposes a minimal state machine for entering and exiting
    Captain's Log mode. Placeholder hooks exist for RAG folder management,
    secure storage, development logging toggles, and encryption integration, but
    they intentionally perform no work in this phase.
    """

    def __init__(self, state: Optional[cl_state.CaptainsLogState] = None) -> None:
        self._state = state or cl_state.get_state()

    # ------------------------------------------------------------------
    # Core mode controls
    # ------------------------------------------------------------------

    def enter_captains_log(self) -> None:
        """Enter Captain's Log mode (no journaling/RAG/encryption yet)."""

        cl_state.enter_captains_log_mode()

    def exit_captains_log(self) -> None:
        """Exit Captain's Log mode."""

        cl_state.exit_captains_log_mode()

    def is_in_captains_log(self) -> bool:
        """Return True if Captain's Log mode is active."""

        return self._state.is_active

    def get_status(self) -> Dict[str, object]:
        """Return a minimal status dictionary for bootup diagnostics."""

        mode = "captains_log" if self.is_in_captains_log() else "normal"
        return {"status": "ok", "mode": mode}

    # ------------------------------------------------------------------
    # Placeholder hooks (no-ops for Phase 1)
    # ------------------------------------------------------------------

    def ensure_rag_folder(self) -> None:
        """Placeholder for RAG folder management (no-op)."""

        return None

    def configure_secure_storage(self) -> None:
        """Placeholder for secure storage hooks (no-op)."""

        return None

    def start_development_logging(self) -> None:
        """Placeholder for starting development logging (no-op)."""

        return None

    def stop_development_logging(self) -> None:
        """Placeholder for stopping development logging (no-op)."""

        return None

    def setup_encryption(self) -> None:
        """Placeholder for future encryption integration (no-op)."""

        return None

    # ------------------------------------------------------------------
    # Compatibility wrappers (maintain existing call sites)
    # ------------------------------------------------------------------

    def enter(self) -> None:
        """Compatibility wrapper for ``enter_captains_log``."""

        self.enter_captains_log()

    def exit(self) -> None:
        """Compatibility wrapper for ``exit_captains_log``."""

        self.exit_captains_log()

    def is_active(self) -> bool:
        """Compatibility wrapper for ``is_in_captains_log``."""

        return self.is_in_captains_log()


_manager = CaptainsLogManager()


def get_manager() -> CaptainsLogManager:
    """Return the shared Captain's Log manager instance."""

    return _manager
