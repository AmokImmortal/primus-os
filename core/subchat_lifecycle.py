# /core/subchat_lifecycle.py

class SubchatLifecycle:
    """
    Handles subchat creation → activation → pause → resume → termination.
    Decoupled from routing, permissions, and security.
    """

    def __init__(self, state, registry, policy):
        """
        state: SubchatState instance (tracks each subchat’s status)
        registry: AgentRegistry instance (for validating assigned agents)
        policy: SubchatPolicy instance (for permission checks)
        """
        self.state = state
        self.registry = registry
        self.policy = policy

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    def create_subchat(self, subchat_id: str, owner: str, assigned_agent: str, metadata=None):
        """Create a new subchat if allowed."""
        if self.state.exists(subchat_id):
            raise ValueError(f"Subchat '{subchat_id}' already exists.")

        if not self.registry.agent_exists(assigned_agent):
            raise ValueError(f"Assigned agent '{assigned_agent}' does not exist.")

        # Check policy
        self.policy.validate_subchat_creation(owner, assigned_agent)

        self.state.create(subchat_id, owner, assigned_agent, metadata)
        return True

    # ---------------------------------------------------------
    # ACTIVATE
    # ---------------------------------------------------------
    def activate_subchat(self, subchat_id: str,