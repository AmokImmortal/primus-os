"""
subchat_isolation.py
--------------------------------
Enforces strict isolation between sub-chats, prevents unauthorized cross-chat
access, protects Captain’s Log subchats, and provides controlled, auditable
exceptions only when the system owner explicitly approves it.

This module is central to PRIMUS Phase 2 (Core Completion).
"""

import os
import json
from typing import Optional, Dict, List


class SubchatIsolationManager:
    """
    Enforces:
      - Strict separation of all subchats
      - No agent may read another agent’s subchat unless owner-approved
      - Captain's Log subchats are completely invisible and inaccessible
      - Read/write rules depend on permissions + protected flags
      - All violations raise explicit errors
    """

    def __init__(self, base_path: str):
        self.base_path = base_path.replace("\\", "/")

        self.captains_log_path = f"{self.base_path}/captains_log"
        self.subchat_root = f"{self.base_path}/subchats"

        self.protected_prefix = "CL_"  # any folder starting with this is INVISIBLE

    # -------------------------------------------------------------
    # INTERNAL UTILITIES
    # -------------------------------------------------------------

    def _is_protected(self, folder: str) -> bool:
        """Captain’s Log subchats are completely invisible unless explicitly unlocked."""
        return folder.startswith(self.protected_prefix)

    def _full_path(self, folder: str) -> str:
        return f"{self.subchat_root}/{folder}"

    def _exists(self, folder: str) -> bool:
        return os.path.isdir(self._full_path(folder))

    # -------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------

    def list_visible_subchats(self, include_system: bool = False) -> List[str]:
        """
        Returns a list of subchats that ARE visible/accessible.
        Captain’s Log subchats are NEVER shown.
        """
        if not os.path.isdir(self.subchat_root):
            return []

        all_chats = os.listdir(self.subchat_root)
        visible = [
            c for c in all_chats
            if not self._is_protected(c)
        ]

        if include_system:
            return visible
        else:
            # Filter out any system-only folders if we add them later
            return visible

    def read_subchat(self, requester: str, folder: str, approved: bool = False) -> str:
        """
        Reads a subchat transcript ONLY IF:
           - It's not protected (Captain’s Log)
           - The requester owns it OR
           - The owner explicitly approved access ("approved=True")

        Otherwise raises an error.
        """
        if self._is_protected(folder):
            raise PermissionError("Access denied: Captain’s Log subchats are invisible.")

        if not approved:
            # Without approval, cross-subchat reads are forbidden
            if requester != folder:
                raise PermissionError(
                    f"Requester '{requester}' cannot access subchat '{folder}' "
                    "without explicit owner approval."
                )

        full_file = f"{self._full_path(folder)}/chat.json"
        if not os.path.isfile(full_file):
            return ""

        with open(full_file, "r", encoding="utf-8") as f:
            return f.read()

    def write_subchat(self, requester: str, folder: str, content: str, approved: bool = False):
        """
        Writes to a subchat ONLY IF:
            - requester == folder owner OR
            - explicit owner approval provided
        Captain’s Log subchats can ONLY be written by the Captains Log Manager.
        """
        if self._is_protected(folder):
            raise PermissionError("Write denied: Captain’s Log subchats require CL manager.")

        if requester != folder and not approved:
            raise PermissionError(
                f"Requester '{requester}' cannot write to subchat '{folder}' without approval."
            )

        os.makedirs(self._full_path(folder), exist_ok=True)
        full_file = f"{self._full_path(folder)}/chat.json"

        with open(full_file, "w", encoding="utf-8") as f:
            f.write(content)

    def request_access(self, requester: str, target: str) -> Dict[str, str]:
        """
        Standardized request packet for PRIMUS approval system.
        """
        if self._is_protected(target):
            return {
                "status": "DENIED",
                "reason": "Target subchat is Captain’s Log protected.",
                "requester": requester,
                "target": target
            }

        return {
            "status": "REQUIRES_APPROVAL",
            "requester": requester,
            "target": target,
            "reason": "Cross-subchat access requires owner approval."
        }

    def safe_delete_subchat(self, requester: str, folder: str, approved: bool = False):
        """
        Deletes a subchat only if:
            - It is not Captain’s Log
            - The requester is the owner OR owner approval exists
        """
        if self._is_protected(folder):
            raise PermissionError("Delete denied: Captain’s Log subchats are protected.")

        if requester != folder and not approved:
            raise PermissionError(
                f"Requester '{requester}' cannot delete subchat '{folder}' without approval."
            )

        full_path = self._full_path(folder)
        if os.path.isdir(full_path):
            for file in os.listdir(full_path):
                try:
                    os.remove(f"{full_path}/{file}")
                except:
                    pass
            os.rmdir(full_path)


# ----------------------------------------------------------------------
# FACTORY FUNCTION
# ----------------------------------------------------------------------

def load_subchat_isolation_manager(system_root: str) -> SubchatIsolationManager:
    """
    Central loader used by PRIMUS runtime.
    """
    return SubchatIsolationManager(base_path=system_root)