from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SubchatManager:
    """
    Minimal SubChat manager that discovers JSON descriptors under subchats/.
    """

    REQUIRED_FIELDS = {"id", "name", "description", "system_prompt"}

    def __init__(self, system_root: str | Path) -> None:
        self.system_root = Path(system_root)
        self.subchats_dir = self.system_root / "subchats"

    def _iter_subchat_files(self) -> List[Path]:
        if not self.subchats_dir.exists():
            return []
        return sorted(self.subchats_dir.glob("*.json"))

    def _load_subchat(self, path: Path) -> Optional[Dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load subchat %s: %s", path, exc)
            return None

        if not isinstance(data, dict):
            logger.warning("Subchat file %s is not a JSON object; skipping.", path)
            return None

        data.setdefault("id", path.stem)
        missing = self.REQUIRED_FIELDS - set(k for k, v in data.items() if v)
        if missing:
            logger.warning("Subchat %s missing required fields %s; skipping.", path, missing)
            return None

        return data

    def list_subchats(self) -> List[Dict[str, str]]:
        subchats: List[Dict[str, str]] = []
        try:
            for path in self._iter_subchat_files():
                data = self._load_subchat(path)
                if data is None:
                    continue
                # Only expose summary fields for listings
                subchats.append(
                    {
                        "id": data.get("id", path.stem),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Subchat discovery failed: %s", exc)
            return []
        return subchats

    def get_subchat(self, subchat_id: str) -> Optional[Dict[str, str]]:
        try:
            for path in self._iter_subchat_files():
                data = self._load_subchat(path)
                if data is None:
                    continue
                candidate_id = data.get("id") or path.stem
                if candidate_id == subchat_id or path.stem == subchat_id:
                    return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Subchat lookup failed for %s: %s", subchat_id, exc)
            return None
        return None

    def status(self) -> Dict[str, object]:
        try:
            subchats = self.list_subchats()
            count = len(subchats)
            return {
                "status": "ok",
                "configured": bool(count),
                "count": count,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Subchat status check failed: %s", exc)
            return {"status": "error", "configured": False, "count": 0}


def get_subchat_manager(system_root: str | Path) -> SubchatManager:
    return SubchatManager(system_root)
