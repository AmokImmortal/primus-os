"""
subchat_schema.py

Defines the strict structural schema all SubChats must follow.
This ensures consistency, validation, and predictable structure
across the entire PRIMUS SubChat ecosystem.
"""

SUBCHAT_SCHEMA = {
    "id": {
        "type": "string",
        "required": True,
        "description": "Unique SubChat identifier."
    },
    "parent_id": {
        "type": "string",
        "required": False,
        "description": "ID of parent SubChat, if any."
    },
    "created_at": {
        "type": "string",
        "format": "datetime",
        "required": True,
        "description": "ISO timestamp of SubChat creation."
    },
    "created_by": {
        "type": "string",
        "required": True,
        "description": "System or user identity that initiated the SubChat."
    },
    "purpose": {
        "type": "string",
        "required": True,
        "description": "Short explanation of what the SubChat is for."
    },
    "state": {
        "type": "dict",
        "required": True,
        "description": "Runtime state defined by subchat_state.py."
    },
    "permissions": {
        "type": "dict",
        "required": True,
        "description": "Permission constraints from subchat_access_control.py."
    },
    "policies": {
        "type": "dict",
        "required": True,
        "description": "Behavioral + operational policies from subchat_policy.py."
    },
    "messages": {
        "type": "list",
        "required": True,
        "description": "Message history contained by the SubChat.",
        "item_schema": {
            "sender": {"type": "string", "required": True},
            "timestamp": {"type": "string", "format": "datetime", "required": True},
            "content": {"type": "string", "required": True},
            "agent_id": {"type": "string", "required": False},
        }
    },
    "logs_enabled": {
        "type": "boolean",
        "required": True,
        "description": "Whether this SubChat writes logs (Captain’s Log sandbox always forces False)."
    }
}


def get_schema() -> dict:
    """Return the official SubChat schema."""
    return SUBCHAT_SCHEMA