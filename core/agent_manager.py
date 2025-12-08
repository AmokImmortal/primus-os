# System/core/agent_manager.py
"""
agent_manager.py

PRIMUS OS Agent Manager

Responsible for:
- Discovering available agents under the System/agents directory
- Providing a simple listing of agent names for diagnostics / self-tests
- (Future) Loading and instantiating agent classes

This module is intentionally minimal for now; it focuses on safe initialization
and directory handling so that PrimusCore can depend on it without crashes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("core.agent_manager")


class AgentManager:
    """
    Minimal AgentManager for PRIMUS OS.

    agents_root:
        Directory that contains agent subfolders. Each subfolder may represent
        a distinct agent implementation (e.g. FileAgent, ResearchAgent, etc.).
    """

    def __init__(self, agents_root: Path | str):
        # Normalize to a Path object even if a string is passed.
        self.agents_dir: Path = Path(agents_root)

        # Ensure the directory exists so later code can safely rely on it
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        # Simple in-memory cache for future expansion (e.g. loaded agent objects)
        self._agent_cache: Dict[str, object] = {}

        logger.info("[core.agent_manager] Initialized. AGENTS_DIR=%s", self.agents_dir)

    # ------------------------------------------------------------------
    # Discovery / listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """
        Return a sorted list of agent directory names.

        This is used by PrimusCore diagnostics to report which agents are
        available on disk. For now we treat any subdirectory as an "agent",
        including __pycache__ (which makes it easy to see what's actually
        present during early development).
        """
        if not self.agents_dir.exists():
            return []

        names: List[str] = []
        for entry in self.agents_dir.iterdir():
            if entry.is_dir():
                names.append(entry.name)

        names.sort()
        return names

    # ------------------------------------------------------------------
    # (Future) Agent loading
    # ------------------------------------------------------------------

    def get_agent(self, name: str) -> Optional[object]:
        """
        Placeholder for future agent loading.

        For now, this just looks in the internal cache and does NOT attempt
        dynamic imports. It exists so PrimusCore can later be extended without
        changing this interface.
        """
        return self._agent_cache.get(name)

    def register_agent(self, name: str, agent_obj: object) -> None:
        """
        Manually register an agent instance in the manager cache.

        This is primarily for future expansion and tests; not used heavily yet.
        """
        self._agent_cache[name] = agent_obj


# ----------------------------------------------------------------------
# Singleton-style accessor
# ----------------------------------------------------------------------

_agent_manager_singleton: Optional[AgentManager] = None


def get_agent_manager(agents_root: Optional[Path | str] = None) -> AgentManager:
    """
    Return a singleton AgentManager instance.

    If agents_root is not provided, it defaults to:
        <System root>/agents
    where <System root> is inferred from this file's location.
    """
    global _agent_manager_singleton

    if _agent_manager_singleton is None:
        if agents_root is None:
            system_root = Path(__file__).resolve().parents[1]
            agents_root = system_root / "agents"

        _agent_manager_singleton = AgentManager(agents_root)

    return _agent_manager_singleton