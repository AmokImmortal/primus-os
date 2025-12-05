import json
from pathlib import Path
from typing import Optional


class SubChatRestore:
    """
    Handles restoring SubChat data from backups created by SubChatBackup.
    Integrates with recovery and storage layers to ensure smooth restoration.
    """

    def __init__(self, backup_dir: str = "subchat_backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def list_backups(self) -> list:
        """
        Returns a list of available backup files sorted newest → oldest.
        """
        backups = sorted(self.backup_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        return [b.name for b in backups]

    def load_backup(self, backup_name: str) -> Optional[dict]:
        """
        Loads a backup file and returns its data.
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            return None

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def restore_subchat(self, subchat_id: str, backup_name: str, storage_handler) -> bool:
        """
        Restores a SubChat from a backup and writes the restored data into the storage layer.

        Parameters:
            subchat_id: ID of the SubChat being restored
            backup_name: name of backup file
            storage_handler: instance of subchat_storage.SubChatStorage
        """
        data = self.load_backup(backup_name)
        if not data:
            return False

        # Ensure the backup actually corresponds to the requested SubChat
        if data.get("subchat_id") != subchat_id:
            return False

        try:
            storage_handler.save_state(subchat_id, data.get("state", {}))
            storage_handler.save_metadata(subchat_id, data.get("metadata", {}))
            storage_handler.save_messages(subchat_id, data.get("messages", []))
            return True
        except Exception:
            return False

    def full_restore(self, backup_name: str, storage_handler) -> bool:
        """
        Restores ALL SubChats present in a full-backup file.
        Only used when performing system-wide rollback.
        """
        data = self.load_backup(backup_name)
        if not data or "subchats" not in data:
            return False

        try:
            for subchat_id, content in data["subchats"].items():
                storage_handler.save_state(subchat_id, content.get("state", {}))
                storage_handler.save_metadata(subchat_id, content.get("metadata", {}))
                storage_handler.save_messages(subchat_id, content.get("messages", []))
            return True
        except Exception:
            return False


if __name__ == "__main__":
    # Manual test
    restore = SubChatRestore()
    print("Available backups:", restore.list_backups())