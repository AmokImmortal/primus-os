# dispatcher.py
"""
PRIMUS Dispatcher (Milestone 2)
Handles routing tasks to agents located in System/agents/*
"""

import importlib
import os
import json

# Path to system paths config
PATHS_FILE = "C:\\P.R.I.M.U.S OS\\System\\configs\\system_paths.json"

class Dispatcher:
    def __init__(self):
        self.paths = self._load_paths()

    def _load_paths(self):
        """
        Load system paths JSON and return dict.
        """
        try:
            with open(PATHS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[dispatcher] Failed to load {PATHS_FILE}: {e}")
            return {}

    def _import_agent(self, agent_name: str):
        """
        Dynamically import agent module.
        Agents follow this structure:

        System/
          agents/
            AgentName/
              agent_name.py
              __init__.py
        """

        # Example: "FileAgent" -> module path "agents.FileAgent.file_agent"
        module_path = f"agents.{agent_name}.file_agent"
        try:
            module = importlib.import_module(module_path)
            return module
        except Exception as e:
            return {
                "status": "error",
                "error": f"Import failed for agent '{agent_name}': {e}"
            }

    def dispatch(self, task: dict):
        """
        Routes a task to its agent.

        Required structure:
        {
            "agent": "FileAgent",
            "action": "ping"
        }
        """
        agent_name = task.get("agent")
        if not agent_name:
            return {"status": "error", "error": "Missing 'agent' field"}

        module = self._import_agent(agent_name)

        # If agent import returned an error dict
        if isinstance(module, dict) and module.get("status") == "error":
            return module

        # Ensure 'handle' exists
        if not hasattr(module, "handle"):
            return {
                "status": "error",
                "error": f"Agent '{agent_name}' has no handle(task) function"
            }

        try:
            return module.handle(task)
        except Exception as e:
            return {"status": "error", "error": f"Agent execution error: {e}"}


# Test entry for boot
def test_dispatcher():
    """
    Called by boot.py to confirm dispatcher works.
    Sends a ping to FileAgent.
    """
    d = Dispatcher()
    return d.dispatch({"agent": "FileAgent", "action": "ping"})


if __name__ == "__main__":
    print(test_dispatcher())