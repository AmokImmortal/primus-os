# /core/subchat_recovery.py

import json
import os
from typing import Optional, Dict, Any

class SubChatRecovery:
    """
    Responsible for restoring SubChat state after crashes, corruption,
    or unexpected shutdowns. Works with subchat_storage.py and subchat_state.py.
    """

    def __init__(self, recovery_folder: str = "System/subchat_recovery"):
        self.recovery_folder = recovery_folder
        os.makedirs(self.recovery_folder, exist_ok=True)

    def get_recovery_file(self, subchat_id: str) -> str:
        return os.path.join(self.recovery_folder, f"{subchat_id}_recovery.json")

    def save_recovery_state(self, subchat_id: str, state: Dict[str, Any]) -> None:
        """
        Saves the most recent working state of a SubChat.
        This gets updated after every major action by subchat_state.py or subchat_engine.py.
        """
        try:
            filepath = self.get_recovery_file(subchat_id)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            print(f"[RECOVERY ERROR] Failed saving state for {subchat_id}: {e}")

    def load_recovery_state(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        """
        Tries to load a SubChat recovery snapshot.
        Returns None if not found or unreadable.
        """
        try:
            filepath = self.get_recovery_file(subchat_id)
            if not os.path.exists(filepath):
                return None

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"[RECOVERY ERROR] Failed loading state for {subchat_id}: {e}")
            return None

    def attempt_recovery(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        """
        Main entry point for SubChat recovery.
        If recovery state exists, returns it.
        Otherwise returns None, meaning a fresh SubChat must be created.
        """
        state = self.load_recovery_state(subchat_id)
        if state:
            print(f"[RECOVERY] SubChat '{subchat_id}' restored from recovery snapshot.")
            return state

        print(f"[RECOVERY] No recovery data for SubChat '{subchat_id}'. Fresh start required.")
        return None

    def delete_recovery_state(self, subchat_id: str) -> None:
        """
        Deletes a recovery snapshot after a SubChat successfully stabilizes.
        """
        try:
            filepath = self.get_recovery_file(subchat_id)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"[RECOVERY ERROR] Failed deleting recovery state for {subchat_id}: {e}")