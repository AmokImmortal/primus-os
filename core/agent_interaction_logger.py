import os
import json
import datetime
from threading import Lock

class AgentInteractionLogger:
    """
    Logs:
        - agent → agent communication
        - primus → agent communication
        - agent → primus communication
        - system events (security, guard blocks, sandbox warnings)
    """

    def __init__(self, root_path=".", log_dir="logs/agent_interactions"):
        self.root_path = root_path
        self.log_dir = os.path.join(root_path, log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        self.lock = Lock()

    def _timestamp(self):
        return datetime.datetime.utcnow().isoformat()

    def _log_path(self):
        date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{date}.log")

    def _write(self, record: dict):
        record["timestamp"] = self._timestamp()

        with self.lock:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ──────────────────────────────────────────────
    # Logging Functions
    # ──────────────────────────────────────────────

    def log_agent_to_agent(self, sender: str, receiver: str, message: str, allowed: bool):
        self._write({
            "type": "agent_to_agent",
            "sender": sender,
            "receiver": receiver,
            "message": message,
            "allowed": allowed
        })

    def log_primus_to_agent(self, primus_id: str, agent: str, message: str):
        self._write({
            "type": "primus_to_agent",
            "primus": primus_id,
            "agent": agent,
            "message": message
        })

    def log_agent_to_primus(self, agent: str, primus_id: str, message: str):
        self._write({
            "type": "agent_to_primus",
            "agent": agent,
            "primus": primus_id,
            "message": message
        })

    def log_system_event(self, event_type: str, details: dict):
        self._write({
            "type": "system_event",
            "event": event_type,
            "details": details
        })

    # ──────────────────────────────────────────────
    # Helper
    # ──────────────────────────────────────────────

    def get_logs_for_day(self, date: str):
        """
        date format: YYYY-MM-DD
        """
        path = os.path.join(self.log_dir, f"{date}.log")
        if not os.path.exists(path):
            return []

        logs = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    logs.append(json.loads(line.strip()))
                except:
                    pass
        return logs