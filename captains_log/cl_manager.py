from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("captains_log")


class CaptainsLogManager:
    """File-backed Captain's Log manager using JSONL storage."""

    def __init__(self, log_path: Path, max_entries: int = 1000) -> None:
        self.log_path = Path(log_path).resolve()
        self.max_entries = max_entries
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create Captain's Log directory %s: %s", self.log_path.parent, exc)

    def append_entry(self, text: str, level: str = "info") -> None:
        """Append a single entry to the Captain's Log."""

        if not text or not text.strip():
            return

        entry: Dict[str, Any] = {
            "ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "text": text,
            "level": level,
        }
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False))
                handle.write("\n")
            self._trim()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to append Captain's Log entry: %s", exc)

    def read_entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read recent entries from the log, returning up to ``limit`` results."""

        if not self.log_path.exists():
            return []

        entries: List[Dict[str, Any]] = []
        try:
            with self.log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError as exc:  # noqa: BLE001
                        logger.warning("Skipping malformed Captain's Log line in %s: %s", self.log_path, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read Captain's Log entries: %s", exc)
            return []

        if limit is None or limit < 0:
            return entries
        return entries[-limit:]

    def clear(self) -> None:
        """Remove all stored Captain's Log entries."""

        try:
            if self.log_path.exists():
                self.log_path.unlink()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to clear Captain's Log: %s", exc)

    # Backwards-compatibility wrappers ------------------------------------
    def write_entry(self, text: str, *, level: str = "INFO", meta: Optional[Dict[str, Any]] = None) -> None:
        del meta  # meta is ignored in this minimal implementation
        self.append_entry(text=text, level=level)

    def read_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.read_entries(limit=limit)

    # Internal helpers -----------------------------------------------------
    def _trim(self) -> None:
        if self.max_entries is None or self.max_entries <= 0:
            return
        entries = self.read_entries()
        if len(entries) <= self.max_entries:
            return
        trimmed = entries[-self.max_entries :]
        try:
            with self.log_path.open("w", encoding="utf-8") as handle:
                for entry in trimmed:
                    handle.write(json.dumps(entry, ensure_ascii=False))
                    handle.write("\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to trim Captain's Log entries: %s", exc)


_manager: CaptainsLogManager | None = None


def get_manager(system_root: str | Path | None = None) -> CaptainsLogManager:
    """Return a singleton CaptainsLogManager rooted under the system logs directory."""

    global _manager
    if _manager is not None:
        return _manager

    root = Path(system_root).resolve() if system_root is not None else Path(".").resolve()
    log_path = root / "logs" / "captains_log.jsonl"
    _manager = CaptainsLogManager(log_path=log_path, max_entries=1000)
    return _manager
