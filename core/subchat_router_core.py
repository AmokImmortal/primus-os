"""
SubChat Router Core
Location: C:\P.R.I.M.U.S OS\System\core\subchat_router_core.py

Responsibilities:
- Register/unregister subchats
- Route messages between subchats (direct, broadcast, or via predicates)
- Enforce simple access control hooks (if available)
- Emit events to an event bus (if available)
- Log interactions (if a logger module is available)
- Persist routing config / registry to disk

This implementation is intentionally conservative and dependency-light:
- It will import optional integrations (access control, event bus, logger) if present,
  but will still function in a reduced mode if they are missing.
- Uses JSON file persistence for registry/config so it's easy to inspect and backup.
"""

from __future__ import annotations
import os
import json
import threading
import time
import logging
from pathlib import Path
from typing import Any, Dict, Callable, List, Optional

ROOT = Path(__file__).resolve().parents[2]  # .../System/core -> parent is System
CORE_DIR = ROOT / "core"
SUBCHAT_DIR = CORE_DIR / "sub_chats"
ROUTER_CONFIG_PATH = CORE_DIR / "subchat_router_config.json"
REGISTRY_PATH = CORE_DIR / "subchat_registry.json"

logger = logging.getLogger("subchat_router_core")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [subchat_router] %(levelname)s: %(message)s"))
    logger.addHandler(ch)

# Optional integrations (import if available)
try:
    from core.subchat_access_control import AccessControl
except Exception:
    AccessControl = None

try:
    from core.subchat_event_bus import SubChatEventBus
except Exception:
    SubChatEventBus = None

try:
    from agent_interaction_logger import AgentInteractionLogger
except Exception:
    AgentInteractionLogger = None


class SubchatRecord(dict):
    """
    Simple dict-like record for registered subchat metadata.
    Example fields:
      - id (str)
      - name (str)
      - owner (str)
      - tags (list)
      - permissions (dict)
      - created_at (float)
      - last_seen (float)
    """

    def touch(self):
        self["last_seen"] = time.time()


class SubchatRouterCore:
    def __init__(self, config_path: Path = ROUTER_CONFIG_PATH, registry_path: Path = REGISTRY_PATH):
        self.config_path = Path(config_path)
        self.registry_path = Path(registry_path)
        self._lock = threading.RLock()
        self.config: Dict[str, Any] = {}
        self.registry: Dict[str, SubchatRecord] = {}
        self.access_control = AccessControl() if AccessControl else None
        self.event_bus = SubChatEventBus() if SubChatEventBus else None
        self.interaction_logger = AgentInteractionLogger() if AgentInteractionLogger else None

        # load persisted state
        self._load_config()
        self._load_registry()

    # -------------------------
    # Persistence
    # -------------------------
    def _load_config(self):
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = {"allow_agent_to_agent": False, "max_concurrent_pairs": 2}
                self._save_config()
            logger.debug("Router config loaded.")
        except Exception as e:
            logger.warning("Failed to load router config: %s", e)
            self.config = {"allow_agent_to_agent": False, "max_concurrent_pairs": 2}

    def _save_config(self):
        try:
            os.makedirs(self.config_path.parent, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent