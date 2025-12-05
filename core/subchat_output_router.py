"""
subchat_output_router.py
Routes processed SubChat output to the correct targets:
- UI renderer
- logs
- parent chats (if allowed)
- agents (if allowed)
- exports (optional)
"""

class SubChatOutputRouter:
    def __init__(self, renderer, logger, policy):
        """
        renderer: UI rendering layer
        logger: system logger
        policy: subchat_policy instance
        """
        self.renderer = renderer
        self.logger = logger
        self.policy = policy

    def route_output(self, subchat_id, message, metadata=None):
        """Main entrypoint for routing outgoing SubChat messages."""
        metadata = metadata or {}

        # Log the outgoing message
        self.logger.info(
            f"[SubChat:{subchat_id}] OUT → {message} | meta={metadata}"
        )

        # Render to UI
        self._send_to_ui(subchat_id, message)

        # Export if allowed
        if self.policy.allows_export(subchat_id):
            self._export_message(subchat_id, message, metadata)

        # Notify parent chat if allowed
        if self.policy.allows_parent_notification(subchat_id):
            self._notify_parent(subchat_id, message, metadata)

        # Forward to agents if the rules allow it
        if self.policy.allows_agent_forwarding(subchat_id):
            self._forward_to_agents(subchat_id, message, metadata)

    def _send_to_ui(self, subchat_id, message):
        """Send cleaned output to UI renderer."""
        try:
            self.renderer.render_message(subchat_id, message)
        except Exception as e:
            self.logger.error(f"UI render failure in SubChat {subchat_id}: {e}")

    def _export_message(self, subchat_id, message, metadata):
        """Optional export behavior (future use)."""
        # Placeholder for future export targets (files, remote, etc.)
        pass

    def _notify_parent(self, subchat_id, message, metadata):
        """Optional: notify parent chat of a message."""
        # Placeholder for parent dispatch
        pass

    def _forward_to_agents(self, subchat_id, message, metadata):
        """Forward SubChat activity to agents when allowed."""
        # Placeholder for agent routing
        pass