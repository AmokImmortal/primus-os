# file_agent.py
"""
FileAgent — minimal test agent for Milestone 2
Provides simple actions for dispatcher validation.
"""

import os

def handle(task: dict):
    """
    Supported actions:
    - ping  → returns pong
    - read  → reads a file from disk
    """

    action = task.get("action")

    # ---- PING ----
    if action == "ping":
        return {"status": "ok", "result": "pong"}

    # ---- READ ----
    if action == "read":
        path = task.get("path")
        if not path:
            return {"status": "error", "error": "Missing 'path' parameter"}

        try:
            if not os.path.exists(path):
                return {"status": "error", "error": f"File does not exist: {path}"}

            with open(path, "r", encoding="utf-8") as f:
                return {"status": "ok", "result": f.read()}

        except Exception as e:
            return {"status": "error", "error": f"Read error: {e}"}

    # ---- UNKNOWN ----
    return {"status": "error", "error": f"Unknown action '{action}'"}