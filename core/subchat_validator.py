"""
subchat_validator.py
Validates Subchat configuration, permissions, policies, and sandbox rules
before a Subchat session is allowed to run. Nothing executes until this
module clears it as valid.
"""

class SubchatValidator:
    def __init__(self, policy_manager, security_manager):
        self.policy_manager = policy_manager
        self.security_manager = security_manager

    def validate_config(self, config: dict) -> bool:
        """
        Validate basic structure of a subchat configuration.
        Expected keys: name, parent_agent, mode, permissions
        """
        required = ["name", "parent_agent", "mode", "permissions"]
        missing = [k for k in required if k not in config]

        if missing:
            raise ValueError(f"Subchat config missing keys: {missing}")

        return True

    def validate_permissions(self, permissions: dict, parent_agent: str) -> bool:
        """
        Validate that the requesting agent is allowed to have these permissions.
        """

        # Sandbox rule enforcement
        if permissions.get("sandbox", False):
            if not self.security_manager.is_sandbox_allowed(parent_agent):
                raise PermissionError(
                    f"Agent '{parent_agent}' is NOT allowed to create sandboxed subchats."
                )

        # Check read/write privileges
        read = permissions.get("read", [])
        write = permissions.get("write", [])

        if self.security_manager.is_restricted_agent(parent_agent):
            # Restricted agents cannot request write access
            if write:
                raise PermissionError(
                    f"Agent '{parent_agent}' is restricted and cannot request write access."
                )

        return True

    def validate_policy(self, parent_agent: str, mode: str) -> bool:
        """
        Validate that the subchat purpose/mode is allowed.
        """
        if not self.policy_manager.is_mode_allowed(parent_agent, mode):
            raise PermissionError(
                f"Mode '{mode}' is not allowed for agent '{parent_agent}'."
            )

        return True

    def validate_all(self, config: dict) -> bool:
        """
        Full validation pipeline.
        """
        self.validate_config(config)
        self.validate_permissions(config["permissions"], config["parent_agent"])
        self.validate_policy(config["parent_agent"], config["mode"])
        return True