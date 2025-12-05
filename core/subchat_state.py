"""
subchat_state.py
Manages ephemeral runtime state for each subchat session.
Holds temporary memory, activity flags, active agents, and sandbox states.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import time


@dataclass
class SubchatState:
    subchat_id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    # Runtime flags
    is_active: bool = True
    is_sandbox: bool = False  # e.g., controlled experimentation space inside PRIMUS

    # State containers
    temp_memory: Dict[str, Any] = field(default_factory=dict)  # resets when subchat ends
    active_agents: Dict[str, Any] = field(default_factory=dict)
    user_context: Dict[str, Any] = field(default_factory=dict)

    def touch(self):
        """Update last active timestamp."""
        self.last_active = time.time()

    def store_temp(self, key: str, value: Any):
        self.temp_memory[key] = value
        self.touch()

    def get_temp(self, key: str, default=None):
        return self.temp_memory.get(key, default)

    def add_agent(self, agent_id: str, agent_info: Any):
        self.active_agents[agent_id] = agent_info
        self.touch()

    def remove_agent(self, agent_id: str):
        if agent_id in self.active_agents:
            del self.active_agents[agent_id]
        self.touch()

    def set_user_context(self, key: str, value: Any):
        self.user_context[key] = value
        self.touch()

    def end_session(self):
        """Gracefully shut down subchat state."""
        self.is_active = False
        self.temp_memory.clear()
        self.active_agents.clear()
        self.user_context.clear()
        self.touch()


class SubchatStateManager:
    """Tracks all subchat states across the PRIMUS runtime."""

    def __init__(self):
        self.sessions: Dict[str, SubchatState] = {}

    def create(self, subchat_id: str, sandbox_mode: bool = False) -> SubchatState:
        state = SubchatState(subchat_id=subchat_id, is_sandbox=sandbox_mode)
        self.sessions[subchat_id] = state
        return state

    def get(self, subchat_id: str) -> Optional[SubchatState]:
        return self.sessions.get(subchat_id)

    def destroy(self, subchat_id: str):
        if subchat_id in self.sessions:
            self.sessions[subchat_id].end_session()
            del self.sessions[subchat_id]

    def cleanup_inactive(self, timeout_seconds: int = 3600):
        """Remove stale subchats not touched recently."""
        now = time.time()
        to_remove = [
            sid for sid, state in self.sessions.items()
            if (now - state.last_active) > timeout_seconds
        ]
        for sid in to_remove:
            self.destroy(sid)