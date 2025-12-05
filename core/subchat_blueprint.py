"""
P.R.I.M.U.S OS — Subchat Blueprint
Defines the canonical template every Subchat must follow.

This ensures:
- Structural consistency
- Mandatory metadata is present
- Implements required lifecycle + policy hooks
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import uuid
import time


@dataclass
class SubchatBlueprint:
    """
    Blueprint definition that all subchats must adhere to.
    """

    # --- REQUIRED SYSTEM METADATA ---
    subchat_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    owner: str = "SYSTEM"  # Who created this subchat: PRIMUS / Agent / User
    parent_chat: Optional[str] = None  # ID of the primary chat session

    # --- IDENTITY & PURPOSE ---
    name: str = "Unnamed Subchat"
    description: str = "No description provided."
    purpose: str = "general"

    # --- SECURITY & ACCESS ---
    is_private: bool = False
    requires_password: bool = False
    password_hash: Optional[str] = None
    allowed_agents: List[str] = field(default_factory=list)
    read_only_for_agents: bool = False

    # --- POLICY LAYER ---
    policy_version: str = "1.0"
    allowed_operations: List[str] = field(default_factory=lambda: [
        "read",
        "write",
        "agent_assist"
    ])
    restricted_operations: List[str] = field(default_factory=list)

    # --- STATE MANAGEMENT ---
    active: bool = True
    locked: bool = False
    sandbox_mode: bool = False    # Agents cannot alter anything unless approved

    # --- RUNTIME CONFIGURATION ---
    memory_limit_kb: int = 5120
    audit_enabled: bool = True
    logging_enabled: bool = True
    rate_limit: int = 10  # requests per minute per agent

    # --- INTERNAL DATA STORAGE ---
    metadata: Dict[str, Any] = field(default_factory=dict)
    custom_flags: Dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------
    #  RUNTIME API
    # ---------------------------------------------------

    def update_timestamp(self):
        self.updated_at = time.time()

    def unlock(self):
        self.locked = False
        self.update_timestamp()

    def lock(self):
        self.locked = True
        self.update_timestamp()

    def enable_sandbox(self):
        self.sandbox_mode = True
        self.update_timestamp()

    def disable_sandbox(self):
        self.sandbox_mode = False
        self.update_timestamp()

    def set_private(self, flag: bool):
        self.is_private = flag
        self.update_timestamp()

    def set_password(self, hashed_value: str):
        self.requires_password = True
        self.password_hash = hashed_value
        self.update_timestamp()

    def clear_password(self):
        self.requires_password = False
        self.password_hash = None
        self.update_timestamp()

    def add_agent(self, agent_name: str):
        if agent_name not in self.allowed_agents:
            self.allowed_agents.append(agent_name)
            self.update_timestamp()

    def remove_agent(self, agent_name: str):
        if agent_name in self.allowed_agents:
            self.allowed_agents.remove(agent_name)
            self.update_timestamp()

    def toggle_audit(self, flag: bool):
        self.audit_enabled = flag
        self.update_timestamp()

    def toggle_logging(self, flag: bool):
        self.logging_enabled = flag
        self.update_timestamp()

    def set_policy(self, operations: List[str], restricted: List[str] = None):
        self.allowed_operations = operations
        if restricted:
            self.restricted_operations = restricted
        self.update_timestamp()


# Factory shortcut
def create_blueprint(**kwargs) -> SubchatBlueprint:
    """
    Helper function to create a subchat blueprint with overrides.
    """
    return SubchatBlueprint(**kwargs)