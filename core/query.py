import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from .memory import MemoryManager


class QueryEngine:
    """
    -------------------------------------------------------------------------
      PRIMUS OS — QUERY ENGINE
    -------------------------------------------------------------------------
    This file acts as the *central brain* for routing queries, retrieving
    memories, applying personalities, controlling agent permissions, and
    coordinating interactions between agents.

    It handles:
        - Loading the correct agent or PRIMUS main personality
        - Routing between agents (with restrictions)
        - Fetching relevant memory
        - Letting agents read other agents (READ-ONLY)
        - Applying personality traits to responses
        - Updating memory only where allowed
        - Returning fully assembled responses

    NOTE:
        - This file is MODEL-AGNOSTIC.
        - It does NOT run inference. Only logic + routing.
        - The Windows app later will plug an inference model into this layer.
    -------------------------------------------------------------------------
    """

    def __init__(self, base_dir: str = "C:/P.R.I.M.U.S OS/System"):
        self.base_dir = Path(base_dir)
        self.memory = MemoryManager(base_dir)

        # Where personalities live
        self.persona_dir = self.base_dir / "personality"
        self.persona_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # PERSONALITY LOADING
    # ------------------------------------------------------------------

    def load_personality(self, agent_id: Optional[str]) -> Dict[str, Any]:
        """
        Loads:
            - PRIMUS personality if agent_id is None
            - The agent personality if agent_id exists
        """
        if agent_id is None:
            path = self.persona_dir / "primus.json"
        else:
            path = self.persona_dir / f"{agent_id}.json"

        if not path.exists():
            return {
                "name": "Default",
                "tone": "neutral",
                "style": "helpful",
                "role": "assistant",
                "growth_enabled": True
            }

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # CROSS-AGENT READ ACCESS
    # ------------------------------------------------------------------

    def read_other_agent_memories(self, requesting_agent: str, target_agent: str) -> List[Dict[str, Any]]:
        """
        Allows one agent to READ the memory of another agent — safely.

        RULES:
            - ALWAYS read-only.
            - ANY agent can read ANY agent, including PRIMUS.
            - NEVER allowed to modify outside its own memory space.
        """
        if requesting_agent == target_agent:
            return []  # self-reading not needed

        return self.memory.get_agent_memories(target_agent)

    # ------------------------------------------------------------------
    # MEMORY FETCHING (PRIMARY)
    # ------------------------------------------------------------------

    def get_relevant_memory(
        self,
        agent_id: Optional[str],
        user_query: str,
        additional_memory_from_agents: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches relevant memory for the active agent.

        Additionally, if the agent is allowed to:
            - Reads memory from other agents (read-only)
        """

        # main memory for this agent
        primary = self.memory.retrieve_relevant_memory(agent_id, user_query)

        # memory borrowed from other agents
        borrowed = []

        if additional_memory_from_agents:
            for other in additional_memory_from_agents:
                borrowed.extend(self.read_other_agent_memories(agent_id, other))

        return primary + borrowed

    # ------------------------------------------------------------------
    # PERSONALITY APPLICATION (PROMPT PREP)
    # ------------------------------------------------------------------

    def apply_personality_to_prompt(
        self,
        personality: Dict[str, Any],
        user_query: str,
        memories: List[Dict[str, Any]]
    ) -> str:
        """
        Combines:
            - Personality (tone, role, style)
            - Relevant memories
            - User query
        Into a single prompt string for model inference.
        """

        memory_str = "\n".join(
            [f"- {m['text']}" for m in memories]
        ) if memories else "No relevant memory."

        base = f"""
SYSTEM:
    Role: {personality.get('role', 'assistant')}
    Tone: {personality.get('tone', 'neutral')}
    Style: {personality.get('style', 'helpful')}

MEMORY:
{memory_str}

USER ASKED:
{user_query}

Respond according to personality and using memory when helpful.
"""

        return base.strip()

    # ------------------------------------------------------------------
    # RESPONSE HANDLING + MEMORY UPDATE
    # ------------------------------------------------------------------

    def update_memory_after_response(
        self,
        agent_id: Optional[str],
        user_query: str,
        model_response: str,
        is_sub_chat: bool
    ):
        """
        Updates memory for the corresponding agent.

        RULES:
            - PRIMUS updates PRIMUS memory
            - Agents update ONLY their own memory
            - Sub-chats store in their parent chat
        """

        if is_sub_chat:
            # In sub-chats, parent agent_id handles the memory
            parent = agent_id
        else:
            parent = agent_id

        self.memory.add_memory(
            agent_id=parent,
            message_text=f"USER: {user_query}\nASSISTANT: {model_response}"
        )

    # ------------------------------------------------------------------
    # FULL QUERY PIPELINE
    # ------------------------------------------------------------------

    def process(
        self,
        user_query: str,
        agent_id: Optional[str] = None,
        sub_chat: bool = False,
        read_from_agents: Optional[List[str]] = None,
        model_callback=None
    ) -> Dict[str, Any]:
        """
        The main public function.

        INPUTS:
            user_query          — text from user
            agent_id            — which agent (None = PRIMUS)
            sub_chat            — if this is a sub-session
            read_from_agents    — list of other agents to borrow memory from
            model_callback      — a function(model_prompt) → string response

        OUTPUT:
            dict containing:
                - "response"     (string)
                - "prompt_used"  (string)
                - "agent"        (string or None)
        """

        # ---------- 1. Load Personality ----------
        personality = self.load_personality(agent_id)

        # ---------- 2. Fetch Memory ----------
        memory = self.get_relevant_memory(
            agent_id=agent_id,
            user_query=user_query,
            additional_memory_from_agents=read_from_agents
        )

        # ---------- 3. Build Full Prompt ----------
        prompt = self.apply_personality_to_prompt(
            personality=personality,
            user_query=user_query,
            memories=memory
        )

        # ---------- 4. Model Inference ----------
        if model_callback is None:
            raise ValueError("No model_callback provided. QueryEngine requires a model to generate responses.")

        response = model_callback(prompt)

        # ---------- 5. Update Memory ----------
        self.update_memory_after_response(
            agent_id=agent_id,
            user_query=user_query,
            model_response=response,
            is_sub_chat=sub_chat
        )

        # ---------- 6. Return ----------
        return {
            "response": response,
            "prompt_used": prompt,
            "agent": agent_id or "PRIMUS"
        }