import time
from typing import Optional, Dict, Any

from core.agent_communication_guard import AgentCommunicationGuard
from core.primus_bridge import PrimusBridge
from core.security_layer import SecurityLayer
from utils.log_utils import log_event, log_error


class AgentMessaging:
    """
    Handles approved message delivery between agents.
    - Enforces communication permissions through AgentCommunicationGuard.
    - Logs all messages (unless in Captain’s Log Sandbox Mode).
    - Routes messages through PrimusBridge for execution.
    """

    def __init__(self, guard: AgentCommunicationGuard, bridge: PrimusBridge, security: SecurityLayer):
        self.guard = guard
        self.bridge = bridge
        self.security = security

    # ---------------------------------------------------------
    #  Send a message from one agent to another
    # ---------------------------------------------------------
    async def send_agent_message(
        self,
        sender_id: str,
        recipient_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        metadata = metadata or {}

        try:
            # 1. Check if communication is allowed
            allowed, reason = self.guard.verify_agent_to_agent(sender_id, recipient_id)
            if not allowed:
                log_event(
                    "agent_message_blocked",
                    {
                        "sender": sender_id,
                        "recipient": recipient_id,
                        "reason": reason,
                        "message_preview": message[:200]
                    }
                )
                return {
                    "status": "blocked",
                    "reason": reason
                }

            # 2. Security Layer Verifies Message Safety
            safety_ok, safety_reason = self.security.evaluate_agent_message(sender_id, message)
            if not safety_ok:
                log_event(
                    "agent_message_flagged",
                    {
                        "sender": sender_id,
                        "recipient": recipient_id,
                        "reason": safety_reason,
                        "message_preview": message[:200]
                    }
                )
                return {
                    "status": "blocked",
                    "reason": f"Security enforcement: {safety_reason}"
                }

            # 3. Log the message (only if NOT in sandbox mode)
            if not metadata.get("sandbox_mode", False):
                log_event(
                    "agent_message_sent",
                    {
                        "timestamp": time.time(),
                        "sender": sender_id,
                        "recipient": recipient_id,
                        "message": message,
                        "metadata": metadata
                    }
                )

            # 4. Deliver via PrimusBridge (the actual execution layer)
            response = await self.bridge.route_agent_request(
                agent_id=recipient_id,
                request_type="agent_message",
                payload={
                    "from": sender_id,
                    "message": message,
                    "metadata": metadata
                }
            )

            return {
                "status": "delivered",
                "response": response
            }

        except Exception as e:
            log_error("agent_messaging_error", str(e))
            return {
                "status": "error",
                "error": str(e)
            }

    # ---------------------------------------------------------
    #  Broadcast message from one agent to many (max 2 per rules)
    # ---------------------------------------------------------
    async def broadcast(
        self,
        sender_id: str,
        recipient_ids: list,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        results = {}

        # Enforce: max 2 agents communicating simultaneously (your rule)
        if len(recipient_ids) > 2:
            return {
                "status": "blocked",
                "reason": "Recipient list exceeds the 2-agent communication limit."
            }

        for rid in recipient_ids:
            result = await self.send_agent_message(sender_id, rid, message, metadata)
            results[rid] = result

        return {
            "status": "completed",
            "results": results
        }