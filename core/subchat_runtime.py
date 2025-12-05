# /core/subchat_runtime.py

"""
Subchat Runtime Manager
-----------------------
Coordinates all subchat components:
- creation
- execution
- isolation
- security checks
- lifecycle
- events
- state handling
- sandbox mode enforcement
"""

from core.subchat_state import SubchatState
from core.subchat_lifecycle import SubchatLifecycle
from core.subchat_security import SubchatSecurity
from core.subchat_access_control import SubchatAccessControl
from core.subchat_policy import SubchatPolicy
from core.subchat_events import SubchatEvents
from core.subchat_controller import SubchatController
from core.subchat_api import SubchatAPI
from core.subchat_sandbox import SubchatSandbox


class SubchatRuntime:
    """Central engine that runs, manages, and enforces all subchat rules."""

    def __init__(self):
        self.state = SubchatState()
        self.lifecycle = SubchatLifecycle()
        self.security = SubchatSecurity()
        self.access = SubchatAccessControl()
        self.policy = SubchatPolicy()
        self.events = SubchatEvents()
        self.controller = SubchatController()
        self.api = SubchatAPI()
        self.sandbox = SubchatSandbox()

        self.active_subchats = {}

    # ---------------------------------------------------------
    # BOOT & INITIALIZATION
    # ---------------------------------------------------------
    def initialize_runtime(self):
        """Prepares subchat runtime for use."""
        try:
            self.events.log("runtime_boot", "Subchat runtime initializing...")

            self.state.initialize()
            self.policy.load_policies()
            self.sandbox.initialize_sandbox()

            self.events.log("runtime_ready", "Subchat runtime initialized successfully.")
            return True

        except Exception as e:
            self.events.log("runtime_failure",





