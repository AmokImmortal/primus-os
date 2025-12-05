"""
subchat_backup.py
Handles SubChat backup creation, rotation, and rollback recovery.
"""

import json
import gzip
import time
from pathlib import Path
from typing import Optional, Dict, Any


class SubChatBackup:
    def __init__(self, root: str = "C:/P.R.I.M.U.S OS/System/core"):
        self.root = Path(root)
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    def create_backup(self, subchat_id: str, data: Dict[str, Any]) -> Path:
        """
        Creates a compressed backup file for a given SubChat's state.
        """
        ts = self._timestamp()
        backup_file = self.backup_dir / f"{subchat_id}_{ts}.json.gz"

        with gzip.open(backup_file, "wt", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return backup_file

    def list_backups(self, subchat_id: Optional[str] = None) -> Dict[str, list]:
        """
        Returns all backup files for either a specific SubChat or all.
        """
        backups = {}

        for file in self.backup_dir.glob("*.json.gz"):
            name = file.name
            sid = name.split("_")[0]

            if subchat_id and sid != subchat_id:
                continue

            backups.setdefault(sid, []).append(file)

        return backups

    def load_backup(self, backup_file: Path) -> Optional[Dict[str, Any]]:
        """
        Loads backup from disk and returns the stored data.
        """
        if not backup_file.exists():
            return None

        with gzip.open(backup_file, "rt", encoding="utf-8") as f:
            return json.load(f)

    def get_latest_backup(self, subchat_id: str) -> Optional[Path]:
        """
        Retrieves the newest backup for a SubChat.
        """
        files = sorted(
            self.backup_dir.glob(f"{subchat_id}_*.json.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return files[0] if files else None

    def rollback(self, subchat_id: str) -> Optional[Dict[str, Any]]:
        """
        Loads and returns the data from the latest backup.
        """
        latest = self.get_latest_backup(subchat_id)
        if not latest:
            return None

        return self.load_backup(latest)

    def cleanup_old_backups(self, keep: int = 10) -> None:
        """
        Keeps only the most recent N backups for all SubChats.
        Prevents storage overload.
        """
        by_chat = self.list_backups()

        for sid, files in by_chat.items():
            files_sorted = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)
            for old in files_sorted[keep:]:
                old.unlink(missing_ok=True)


# Optional utility for scheduled backups
class SubChatBackupScheduler:
    def __init__(self, backup_manager: SubChatBackup, interval_seconds: int = 3600):
        self.manager = backup_manager
        self.interval = interval_seconds
        self._last_run = 0

    def tick(self, subchat_id: str, state: Dict[str, Any]) -> Optional[Path]:
        """
        Call this repeatedly from a main loop. Creates backups on schedule.
        """
        now = time.time()
        if now - self._last_run < self.interval:
            return None

        self._last_run = now
        return self.manager.create_backup(subchat_id, state)