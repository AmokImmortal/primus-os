# core/memory_manager.py

"""
Compatibility shim for PRIMUS OS memory management.

Historically the project imported:

    from core.memory_manager import MemoryManager

but the concrete implementation now lives in core/memory.py.

This module provides:
    - MemoryManager: a direct alias of the implementation class
    - get_memory_manager(): a simple singleton-style accessor
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .memory import MemoryManager as _MemoryManagerImpl


class MemoryManager(_MemoryManagerImpl):
    """
    Thin subclass alias so existing imports of
    `core.memory_manager.MemoryManager` continue to work.
    """
    pass


_memory_manager_singleton: Optional[MemoryManager] = None


def get_memory_manager(memory_root: Optional[str] = None) -> MemoryManager:
    """
    Return a process-wide singleton MemoryManager.

    If memory_root is not provided, default to `<System root>/memory`.
    """
    global _memory_manager_singleton

    if _memory_manager_singleton is None:
        if memory_root is None:
            system_root = Path(__file__).resolve().parents[1]
            memory_root = str(system_root / "memory")

        _memory_manager_singleton = MemoryManager(memory_root=memory_root)

    return _memory_manager_singleton