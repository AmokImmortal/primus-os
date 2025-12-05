"""
subchat_ui_controller.py
High-level controller connecting the UI Adapter to the SubChat Runtime.
Routes UI events → SubChat Runtime, and runtime outputs → UI rendering layer.
"""

from typing import Optional, Dict, Any

from core.subchat_runtime import SubChatRuntime
from core.subchat_ui_adapter import SubChatUIAdapter
from core.subchat_renderer import SubChatRenderer


class SubChatUIController:
    """
    Main coordination layer between the UI (Windows app) and SubChat internal systems.
    Handles:
        • UI → Runtime message flow
        • Runtime → UI rendering
        • Chat window/session lifecycle control
    """

    def __init__(self, runtime: Optional[SubChatRuntime] = None):
        self.runtime = runtime or SubChatRuntime()
        self.ui_adapter = SubChatUIAdapter()
        self.renderer = SubChatRenderer()

    # ----------------------------------------------------------------------
    # Window / Session Handling
    # ----------------------------------------------------------------------

    def create_subchat_window(self, parent_chat_id: str) -> str:
        self.ui_adapter.ensure_ready()

        session_id = self.runtime.create_subchat(parent_chat_id)

        window_id = self.ui_adapter.create_window_for_subchat(session_id)

        return window_id

    def close_subchat_window(self, window_id: str) -> bool:
        session_id = self.ui_adapter.get_session_for_window(window_id)
        if not session_id:
            return False

        self.runtime.close_subchat(session_id)
        self.ui_adapter.close_window(window_id)

        return True

    # ----------------------------------------------------------------------
    # Message Flow
    # ----------------------------------------------------------------------

    def handle_user_input(self, window_id: str, text: str) -> Dict[str, Any]:
        """
        From UI → Runtime → Response → Render → UI.
        """

        session_id = self.ui_adapter.get_session_for_window(window_id)
        if not session_id:
            return {"error": "Invalid window"}

        # Send text into SubChat engine
        engine_result = self.runtime.process_user_message(session_id, text)

        # Render output into UI-friendly blocks
        rendered_output = self.renderer.render_output(engine_result)

        # Push into UI layer
        self.ui_adapter.update_window(window_id, rendered_output)

        return {
            "session_id": session_id,
            "rendered_output": rendered_output
        }

    # ----------------------------------------------------------------------
    # System Events
    # ----------------------------------------------------------------------

    def notify_focus_changed(self, window_id: str):
        """Called by UI when the user focuses a SubChat window."""
        session_id = self.ui_adapter.get_session_for_window(window_id)
        if session_id:
            self.runtime.set_chat_focus(session_id)

    def notify_window_resized(self, window_id: str, width: int, height: int):
        """Optional: the renderer can adapt layout."""
        self.renderer.update_layout(width, height)

    # ----------------------------------------------------------------------
    # Debug / Diagnostics
    # ----------------------------------------------------------------------

    def get_runtime_debug_info(self) -> Dict[str, Any]:
        return self.runtime.get_debug_info()

    def get_ui_debug_info(self) -> Dict[str, Any]:
        return self.ui_adapter.get_debug_info()