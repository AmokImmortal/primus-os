# core/memory_manager.py

from __future__ import annotations

"""
core/memory_manager.py

Thin wrapper + singleton accessor around the JSON-based MemoryManager
implemented in core.memory.

This module exists so other parts of PRIMUS can do:

    from core.memory_manager import MemoryManager, get_memory_manager

without worrying about the underlying implementation details.
"""

import logging
from pathlib import Path
from typing import Optional

from core.memory import MemoryManager as _BaseMemoryManager

logger = logging.getLogger("core.memory_manager")

# Singleton instance
_MEMORY_MANAGER: Optional["MemoryManager"] = None


class MemoryManager(_BaseMemoryManager):
    """
    PRIMUS-level MemoryManager.

    Currently this just subclasses the JSON-based MemoryManager from core.memory
    and normalizes the memory_root to live under the System/memory folder.
    """

    def __init__(self, memory_root: Path | str):
        root = Path(memory_root)
        super().__init__(str(root))


def get_memory_manager(system_root: Optional[Path] = None) -> MemoryManager:
    """
    Return a process-wide singleton MemoryManager instance.

    - If system_root is not provided, it defaults to the parent directory of core/.
    - Memory directory is System/memory by default.
    """
    global _MEMORY_MANAGER

    if _MEMORY_MANAGER is not None:
        return _MEMORY_MANAGER

    if system_root is None:
        # .../System/core/memory_manager.py -> .../System
        system_root = Path(__file__).resolve().parents[1]

    memory_root = system_root / "memory"
    logger.info("Initializing MemoryManager with root=%s", memory_root)

    _MEMORY_MANAGER = MemoryManager(memory_root)
    return _MEMORY_MANAGER