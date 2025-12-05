import uuid
from typing import Dict, Any


class SubchatRouter:
    """
    Routes messages between:
      - Main PRIMUS runtime
      - Subchats
      - Agents
      - Sandbox (Captain’s Log) when enabled

    Works together with:
      • subchat_manager
      • agent_messaging
      • agent_permissions
      • agent_interaction_logger
    """

    def __init__(self, subchat_manager, agent_messaging, agent_permissions, logger):
        self.subchat_manager = subchat_manager
        self.agent_messaging = agent_messaging
        self.agent_permissions = agent_permissions
        self.logger = logger

    # ----------------------------------------------------------------------
    # MAIN ENTRY POINT
    # ----------------------------------------------------------------------
    def route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        MAIN dispatch function.
        Payload example:
        {
            "from": "primus" | "agent" | "subchat",
            "target": "agent" | "subchat" | "primus",
            "agent_id": "...",
            "subchat_id": "...",
            "message": "User said blah blah"
        }
        """

        origin = payload.get("from")
        target = payload.get("target")

        # --- Validate Permissions ------------------------------------------------
        if not self.agent_permissions.validate(payload):
            return {"status": "denied", "reason": "permission denied"}

        # ----------------------------------------------------------------------
        # Routing Logic
        # ----------------------------------------------------------------------
        if target == "agent":
            return self._route_to_agent(payload)

        if target == "subchat":
            return self._route_to_subchat(payload)

        if target == "primus":
            return self._route_to_primus(payload)

        return {"status": "error", "reason": "invalid target"}

    # ----------------------------------------------------------------------
    # SUB-ROUTES
    # ----------------------------------------------------------------------
    def _route_to_agent(self, payload: Dict[str, Any]):
        agent_id = payload.get("agent_id")
        msg = payload.get("message")

        result = self.agent_messaging.send_to_agent(agent_id, msg)
        self.logger.record_interaction("subchat_router", "agent", msg)

        return {"status": "ok", "response": result}

    def _route_to_subchat(self, payload: Dict[str, Any]):
        subchat_id = payload.get("subchat_id")
        msg = payload.get("message")

        subchat = self.subchat_manager.get_subchat(subchat_id)
        if not subchat:
            return {"status": "error", "reason": "subchat not found"}

        response = subchat.process_message(msg)

        self.logger.record_interaction("subchat_router", "subchat", msg)

        return {"status": "ok", "response": response}

    def _route_to_primus(self, payload: Dict[str, Any]):
        msg = payload.get("message")

        self.logger.record_interaction("subchat_router", "primus", msg)

        # PRIMUS core processing — replaced later with runtime hook
        return {
            "status": "ok",
            "response": f"PRIMUS received: {msg}"
        }

    # ----------------------------------------------------------------------
    # SYSTEM UTIL
    # ----------------------------------------------------------------------
    def create_subchat(self, name: str, owner: str = "user") -> str:
        subchat_id = str(uuid.uuid4())
        self.subchat_manager.create_subchat(subchat_id, name, owner)

        return subchat_id