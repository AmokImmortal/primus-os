"""
PRIMUS — Hybrid Version (Detailed + Fully Runnable)

This file acts as the central brain and security gatekeeper for your multi-agent system.

It loads:
- Personality config
- Security config
- Agent definitions
- Session manager
- RAG access rules
- Agent–Agent permission rules

At runtime it:
1. Initializes system state
2. Enforces security policies
3. Routes messages to the correct agent
4. Logs important events
5. Provides helper utilities for every agent
"""

import json
import os
from typing import Dict, Any, Optional

from core.agent_manager import AgentManager
from core.persona import Persona
from core.session_manager import SessionManager


# ======================================================
#                PRIMUS MAIN CLASS
# ======================================================

class Primus:
    def __init__(self):
        """
        Bootstraps the PRIMUS environment.
        Loads personality, registers agents, and initializes the session system.
        """

        # ------------------------------------------------
        # Load system personality configuration
        # ------------------------------------------------
        self.personality = Persona("system/personality.json")

        # ------------------------------------------------
        # Initialize RAG access locations
        # system_rag     = global read-only RAG
        # private_rag    = ONLY the OWNER (you) can access
        # agent_rag/*    = per-agent local RAG spaces
        # ------------------------------------------------
        self.paths = {
            "system_rag": "rag/system",
            "private_rag": "rag/private",
            "agent_rag": "rag/agents"
        }

        # Make sure folders exist
        for p in self.paths.values():
            os.makedirs(p, exist_ok=True)

        # ------------------------------------------------
        # Initialize supporting components
        # ------------------------------------------------
        self.agent_manager = AgentManager()
        self.session_manager = SessionManager()

        # ------------------------------------------------
        # Register default system agents
        # (These can later be extended dynamically)
        # ------------------------------------------------
        self._register_default_agents()

        # Loaded & ready
        print("[PRIMUS] System initialized successfully.")

    # ==================================================
    #                AGENT REGISTRATION
    # ==================================================
    def _register_default_agents(self):
        """
        Registers all baseline agents that PRIMUS controls.
        Future agents may also be loaded dynamically.
        """

        agents_to_register = [
            {
                "name": "Coordinator",
                "role": "Oversees tasks, assigns agent workloads, manages communication flow.",
                "permissions": {
                    "system_rag_read": True,
                    "private_rag_read": False,
                    "agent_to_agent": True
                }
            },
            {
                "name": "SecurityAgent",
                "role": "Monitors compliance with rules, permissions, and interaction policies.",
                "permissions": {
                    "system_rag_read": True,
                    "private_rag_read": False,
                    "agent_to_agent": True
                }
            },
            {
                "name": "MemoryAgent",
                "role": "Handles storing, retrieving, and summarizing memory within allowed spaces.",
                "permissions": {
                    "system_rag_read": True,
                    "private_rag_read": False,
                    "agent_to_agent": False
                }
            },
        ]

        for a in agents_to_register:
            self.agent_manager.register_agent(
                name=a["name"],
                role=a["role"],
                permissions=a["permissions"]
            )

    # ==================================================
    #       SECURITY: RAG ACCESS ENFORCEMENT
    # ==================================================
    def can_agent_access_rag(
        self,
        agent_name: str,
        rag_type: str
    ) -> bool:
        """
        Enforces RAG access policy.

        rag_type options:
            system   → read-only by all agents unless restricted
            private  → ONLY HUMAN OWNER can read/write
            agent    → per-agent local RAG

        """

        agent = self.agent_manager.get_agent(agent_name)
        if not agent:
            return False

        # Private RAG always blocked for agents
        if rag_type == "private":
            return False

        # System RAG → granted only if permission exists
        if rag_type == "system":
            return agent.permissions.get("system_rag_read", False)

        # Agent local RAG → only the owning agent can access
        if rag_type.startswith("agent:"):
            owner = rag_type.split(":")[1]
            return owner == agent_name

        return False

    # ==================================================
    #         SECURITY: AGENT → AGENT PERMISSIONS
    # ==================================================
    def can_agent_message_agent(
        self,
        sender: str,
        receiver: str
    ) -> bool:
        """
        Enforces agent-to-agent message rules.
        """

        s = self.agent_manager.get_agent(sender)
        r = self.agent_manager.get_agent(receiver)

        if not s or not r:
            return False

        return s.permissions.get("agent_to_agent", False)

    # ==================================================
    #              MAIN ROUTING FUNCTION
    # ==================================================
    def route_message(
        self,
        session_id: str,
        agent_name: str,
        message: str
    ) -> str:
        """
        Core processing pipeline.
        """

        agent = self.agent_manager.get_agent(agent_name)
        if not agent:
            return f"[ERROR] Agent '{agent_name}' does not exist."

        # Store message inside session
        self.session_manager.add_message(
            session_id=session_id,
            sender=agent_name,
            content=message
        )

        # Ask the agent to process the message
        response = agent.run(message)

        # Log the response into the session
        self.session_manager.add_message(
            session_id=session_id,
            sender=f"{agent_name}_response",
            content=response
        )

        return response

    # ==================================================
    #        CREATE PASSWORD-PROTECTED SUBCHATS
    # ==================================================
    def create_private_subchat(
        self,
        name: str,
        password: str,
        security_questions: Dict[str, str]
    ) -> str:
        """
        Creates a private password-protected session.

        name → subchat name
        password → at least 6 char OR 4-digit PIN
        security_questions → dictionary of answers
        """

        if not (
            len(password) >= 6
            or (len(password) == 4 and password.isdigit())
        ):
            return "[ERROR] Password must be 6+ chars OR 4-digit numeric PIN."

        return self.session_manager.create_private_session(
            name=name,
            password=password,
            security_questions=security_questions
        )

    # ==================================================
    #      RESET PASSWORD (SECURITY Q VALIDATION)
    # ==================================================
    def reset_subchat_password(
        self,
        subchat_name: str,
        new_password: str,
        provided_answers: Dict[str, str]
    ) -> str:
        """
        Validates 2/3 security questions,
        then updates password.
        """
        return self.session_manager.reset_password(
            subchat_name=subchat_name,
            new_password=new_password,
            provided_answers=provided_answers
        )


# ======================================================
#                 STANDALONE EXECUTION
# ======================================================

if __name__ == "__main__":
    primus = Primus()
    print("\n[PRIMUS] Ready.\n")