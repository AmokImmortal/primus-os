# bridge.py
"""
Dispatcher Bridge - resolves agent name -> imports module -> calls handle()
Milestone 2 stable version.
"""

import importlib


class Bridge:
    def call_agent(self, agent_name: str, action: str, **kwargs):
        """
        Load agent module dynamically:
        agents.<AgentName>.file_agent
        Example: FileAgent -> agents.FileAgent.file_agent
        """
        try:
            module_path = f"agents.{agent_name}.file_agent"
            agent_module = importlib.import_module(module_path)
        except Exception as e:
            return {
                "status": "error",
                "error": f"Cannot import agent module '{module_path}': {str(e)}"
            }

        if not hasattr(agent_module, "handle"):
            return {
                "status": "error",
                "error": f"Agent module '{module_path}' missing handle()"
            }

        try:
            return agent_module.handle({"action": action, **kwargs})
        except Exception as e:
            return {
                "status": "error",
                "error": f"Agent execution error: {str(e)}"
            }

    def send(self, agent_name, payload):
        """
        Accepts:
            agent_name: "FileAgent"
            payload: {"action": "...", "data": {...}}
        """
        action = payload.get("action")
        data = payload.get("data", {})
        return self.call_agent(agent_name, action, **data)