import json
from pathlib import Path

class AgentPermissions:
    """
    Centralized permission-control system for all PRIMUS agents.
    Enforces:
        - agent-to-agent communication rules
        - RAG access permissions
        - collaboration limits
        - sandbox-mode restrictions
        - capability-based restrictions
        - sub-chat visibility rules
        - approval-required operations
    """

    def __init__(self, primus_state, permissions_file="config/agent_permissions.json"):
        """
        primus_state = reference to primus_runtime global state
                       containing:
                           - sandbox_mode_active
                           - active_agents
                           - collaboration_count
                           - privileged_operations_enabled
        """
        self.primus_state = primus_state
        self.permissions_file = Path(permissions_file)
        self.permissions = self._load_permissions()

        # Default collaboration limit: 2 agents (you can change later)
        self.MAX_COLLABORATION = 2

    # ---------------------------------------------------------
    # CONFIG LOADING
    # ---------------------------------------------------------
    def _load_permissions(self):
        if not self.permissions_file.exists():
            return {}

        try:
            with open(self.permissions_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    # ---------------------------------------------------------
    # AGENT → AGENT COMMUNICATION
    # ---------------------------------------------------------
    def can_agent_message(self, sender_id, receiver_id):
        """
        Returns True if sender is allowed to contact receiver.
        Handles:
            - global sandbox limits
            - per-agent allow/block lists
            - approval-required relationships
            - collaboration limit caps
        """

        # SANDBOX OVERRIDE: no unsolicited agent–agent contact
        if self.primus_state.sandbox_mode_active:
            return False

        # Collaboration limit
        if self.primus_state.collaboration_count >= self.MAX_COLLABORATION:
            return False

        # Get sender permissions
        sender_perm = self.permissions.get(sender_id, {})
        allowed = sender_perm.get("allowed_agents", [])
        blocked = sender_perm.get("blocked_agents", [])
        requires_approval = sender_perm.get("approval_required", [])

        # Hard block
        if receiver_id in blocked:
            return False

        # If explicitly allowed → OK
        if receiver_id in allowed:
            return True

        # If approval required → DEFER (not auto allowed)
        if receiver_id in requires_approval:
            return None  # None = needs Primus confirmation

        # If nothing defined → default deny (safe mode)
        return False

    # ---------------------------------------------------------
    # RAG ACCESS PERMISSIONS
    # ---------------------------------------------------------
    def can_access_rag(self, agent_id, rag_path, access_type="read"):
        """
        Enforce:
            - NO agent can access Captain’s Log RAG
            - Agents can read global RAG
            - Agents can write ONLY to their own RAG folder
            - No access to Private RAG zones
        """

        rag_path = Path(rag_path)

        # Captain’s Log RAG is FORBIDDEN
        if "captains_log" in rag_path.parts:
            return False

        # Private RAG is FORBIDDEN
        if "private" in rag_path.parts:
            return False

        # Allow READ on global RAG
        if access_type == "read" and "rag" in rag_path.parts:
            return True

        # Allow WRITE only to own folder
        if access_type == "write":
            agent_rag_dir = Path("rag") / agent_id
            return agent_rag_dir in rag_path.parents or agent_rag_dir == rag_path

        return False

    # ---------------------------------------------------------
    # SUB-CHAT ACCESS
    # ---------------------------------------------------------
    def can_access_subchat(self, agent_id, parent_chat_owner, is_primus=False):
        """
        Rules:
            - Agents may NOT access PRIMUS private subchats.
            - Agents can access other agent subchats only when:
                * Relevant to their assigned task
                * Primus approved the collaboration
        """

        # No agent may access Primus private subchats
        if is_primus:
            return False

        # If agent is accessing someone else’s subchat → approval required
        return None  # None = requires Primus approval

    # ---------------------------------------------------------
    # SANDBOX MODE PERMISSIONS
    # ---------------------------------------------------------
    def sandbox_allows_operation(self, operation_type):
        """
        Sandbox mode RESTRICTS almost everything.
        Returns True only for "read" or "status" operations.
        """

        if not self.primus_state.sandbox_mode_active:
            return True  # Normal mode → operations allowed

        # Allowed in sandbox:
        SAFE_OPS = ["read", "inspect", "status"]

        return operation_type in SAFE_OPS

    # ---------------------------------------------------------
    # PRIVILEGED OPERATIONS
    # ---------------------------------------------------------
    def can_run_privileged_operation(self, agent_id, operation_name):
        """
        Only PRIMUS in sandbox mode OR the Captain (user) can run privileged ops.
        Agents may *request*, but cannot execute without Primus approval.
        """

        # If sandbox mode is active → NO agent allowed
        if self.primus_state.sandbox_mode_active:
            return False

        # If agent is not whitelisted for privileged ops:
        perms = self.permissions.get(agent_id, {})
        privileged = perms.get("privileged", [])

        return operation_name in privileged

    # ---------------------------------------------------------
    # COLLABORATION PERMISSION
    # ---------------------------------------------------------
    def can_initiate_collaboration(self, agent_id, target_agent):
        """
        Agents requesting collaboration must:
            - be under limit of active collaborations
            - not be in sandbox mode
            - get Primus approval (ALWAYS for now)
        """

        # Sandbox forbids collaboration
        if self.primus_state.sandbox_mode_active:
            return False

        # Collaboration cap
        if self.primus_state.collaboration_count >= self.MAX_COLLABORATION:
            return False

        # Always requires Primus approval (user rule)
        return None  # None = needs approval

    # ---------------------------------------------------------
    # FINAL AUTHORIZATION PROCESSOR
    # ---------------------------------------------------------
    def get_permission_report(self, agent_id):
        """
        Returns a dictionary summarizing an agent’s permissions.
        Used by Primus and by Captain’s Log sandbox interface.
        """

        perms = self.permissions.get(agent_id, {})

        return {
            "allowed_agents": perms.get("allowed_agents", []),
            "blocked_agents": perms.get("blocked_agents", []),
            "approval_required": perms.get("approval_required", []),
            "privileged": perms.get("privileged", []),
            "max_collaboration": self.MAX_COLLABORATION,
            "sandbox_mode": self.primus_state.sandbox_mode_active,
        }