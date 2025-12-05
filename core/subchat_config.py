"""
subchat_config.py
Global configuration options, defaults, and tunable policies shared across
all SubChat components inside PRIMUS Core.
"""

class SubChatConfig:
    """
    Centralized configuration object for SubChat system.
    All modules reference this to keep behavioral consistency.
    """

    # ----- Lifecycle / Runtime -----
    DEFAULT_TIMEOUT_SECONDS = 300
    MAX_CONCURRENT_SUBCHATS = 32
    ENABLE_AUTOCLEAN = True
    AUTOCLEAN_INTERVAL = 120  # seconds

    # ----- Memory & Logging -----
    ENABLE_MEMORY = True
    MEMORY_RETENTION_LIMIT = 50  # messages per SubChat
    ENABLE_EVENT_LOGGING = True
    ENABLE_AUDIT_LOGGING = True

    # ----- Isolation & Security -----
    ENFORCE_SANDBOX_MODE = True
    BLOCK_EXTERNAL_IO = True
    BLOCK_INTERNET_ACCESS = True
    ENFORCE_AGENT_PERMISSIONS = True

    # ----- Message Rules -----
    MAX_MESSAGE_LENGTH = 4000
    MAX_RESPONSE_LENGTH = 6000
    ENABLE_CONTENT_FILTERING = True

    # ----- SubChat Behavior -----
    ALLOW_PARENT_INHERITANCE = True        # SubChats inherit parent personality
    ALLOW_AUTONOMOUS_PERSONALITY = False   # SubChats cannot develop their own personality
    REQUIRE_APPROVAL_FOR_ESCALATION = True # If a SubChat wants to modify global state

    # ----- Sandbox Mode -----
    SANDBOX_STRICT = True      # Prevents ANY system modification until user approval
    SANDBOX_ALLOW_READ = True  # Can read but cannot write outside its container

    @classmethod
    def export(cls) -> dict:
        """Return all config as a dictionary."""
        return {key: getattr(cls, key) for key in dir(cls) if key.isupper()}