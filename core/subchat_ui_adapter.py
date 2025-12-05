from typing import Dict, Any
from .subchat_renderer import SubChatRenderer
from .subchat_router import SubChatRouter
from .subchat_formatter import SubChatFormatter
from .subchat_normalizer import SubChatNormalizer


class SubChatUIAdapter:
    """
    Bridges the SubChat Engine with the Windows UI layer.

    Responsibilities:
      - Accept raw UI events (button press, message typed, mode toggles)
      - Normalize & format user input
      - Route input to the correct SubChat instance
      - Receive rendered output and return UI-ready payloads
    """

    def __init__(self, router: SubChatRouter):
        self.router = router
        self.renderer = SubChatRenderer()
        self.normalizer = SubChatNormalizer()
        self.formatter = SubChatFormatter()

    # -------------------------
    #  Input From UI → SubChat
    # -------------------------
    def handle_ui_message(self, subchat_id: str, message: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Entry point for UI messages. Cleans, normalizes, and passes the
        input to the SubChat system, then returns a UI-safe response dict.
        """

        metadata = metadata or {}

        # Normalize user text
        clean_message = self.normalizer.normalize(message)

        # Route input into subchat core
        response = self.router.route_message(
            subchat_id=subchat_id,
            message=clean_message,
            metadata=metadata
        )

        # Render output to presentable form
        rendered_output = self.renderer.render(response)

        # Format for UI compatibility
        ui_payload = self.formatter.format(rendered_output)

        return {
            "subchat_id": subchat_id,
            "payload": ui_payload,
            "raw_output": response,
            "clean_input": clean_message
        }

    # -------------------------
    #  Control Signals From UI
    # -------------------------
    def handle_ui_event(self, subchat_id: str, event_type: str, event_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Handles UI-triggered events, such as toggling modes,
        resetting chats, switching personalities, etc.
        """

        event_data = event_data or {}

        # Send event to router (router handles lifecycle + state)
        result = self.router.handle_event(
            subchat_id=subchat_id,
            event_type=event_type,
            event_data=event_data
        )

        # Render any response
        if isinstance(result, str):
            # Plain response, still render for UI
            formatted = self.formatter.format(self.renderer.render(result))
        else:
            formatted = result

        return {
            "event": event_type,
            "status": "processed",
            "result": formatted
        }

    # -------------------------
    #  UI Pull API
    # -------------------------
    def fetch_subchat_state_for_ui(self, subchat_id: str) -> Dict[str, Any]:
        """
        Returns UI-ready representation of SubChat state.
        Used for: opening windows, refreshing views, context syncing.
        """

        state = self.router.get_current_state(subchat_id)

        rendered_state = self.renderer.render({
            "system_state": state
        })

        return self.formatter.format(rendered_state)