from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class SubchatManager:
    """
    Minimal placeholder manager for future SubChat support.

    Currently performs light discovery of a subchats directory (if present)
    and exposes status/list helpers for diagnostics.
    """

    def __init__(self, system_root: str | Path) -> None:
        self.system_root = Path(system_root)
        self.subchat_root = self.system_root / "subchats"

    def _discover_subchats(self) -> List[Dict[str, str]]:
        """
        Best-effort discovery of subchat descriptors.

        For now, returns an empty list if the directory is missing or unreadable.
        """
        if not self.subchat_root.exists():
            return []

        subchats: List[Dict[str, str]] = []
        try:
            for path in sorted(self.subchat_root.iterdir()):
                if path.is_dir():
                    subchats.append({"id": path.name, "path": str(path)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Subchat discovery failed: %s", exc)
            return []
        return subchats

    def status(self) -> Dict[str, object]:
        """
        Lightweight status block used by bootup diagnostics.
        """
        subchats = self._discover_subchats()
        return {
            "status": "ok",
            "configured": bool(subchats),
            "count": len(subchats),
        }

    def list_subchats(self) -> List[Dict[str, str]]:
        """
        Return discovered subchats (currently empty unless directories exist).
        """
        return self._discover_subchats()


def get_subchat_manager(system_root: str | Path) -> SubchatManager:
    return SubchatManager(system_root)
