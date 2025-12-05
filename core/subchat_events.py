"""
subchat_events.py
PRIMUS OS — Subchat Event Dispatcher

This module centralizes ALL event handling for subchats.
It connects:
- subchat_lifecycle
- subchat_state
- subchat_security
- subchat_access_control
- subchat_policy
- subchat_router

Its job:
1. Receive an event → ("message", "open", "close", "permission-change", etc.)
2. Validate → Security, access control, policy
3. Forward → lifecycle + router
4. Update → state
5. Log decisions (OPTIONAL — NO captain’s log)

This is the "brain" that orchestrates subchat behavior.
"""

from typing import Dict, Any, Optional, Callable

# Import the pieces (safe-soft imports)
try:
    from .subchat_lifecycle import SubChatLifecycle
    from .subchat_state import SubChatState
    from .subchat_security import SubchatSecurity
    from .subchat_access_control import SubChatAccessControl
    from .subchat_policy import SubChatPolicy
    from .subchat_router import SubChatRouter
except ImportError:
    # Safe fallback for first-boot
    SubChatLifecycle = None
    SubChatState = None
    SubchatSecurity = None
    SubChatAccessControl = None
    SubChatPolicy = None
    SubChatRouter = None


class SubChatEvents:
    def __init__(self, logger=None):
        self.lifecycle = SubChatLifecycle()
        self.state = SubChatState()
        self.security = SubchatSecurity()
        self.access = SubChatAccessControl()
        self.policy = SubChatPolicy()
        self.router = SubChatRouter()

        self.logger = logger  # Should log ONLY normal activity,





