"""
Subchat Access Control for PRIMUS OS

Location:
    C:\P.R.I.M.U.S OS\System\core\subchat_access_control.py

Responsibilities:
- Enforce private vs public subchat rules
- Password protect private subchats (PBKDF2-HMAC hashed)
- Policy-based agent access checks (read/write/route/interop)
- Temporary access tokens (grant/revoke with expiry)
- Audit logging of access decisions
- Simple JSON-backed persistent policy store

Notes:
- Designed to be file-backed and dependency-light (std-lib only).
- Integrates with higher-level modules by calling can_agent_access(...)
- Persists to core/access_control.json and writes logs to core/logs/access_control.log
"""

from __future__ import annotations
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from hashlib import pbkdf2_hmac
from typing import Dict, List, Optional, Tuple, Any

# Paths (relative to System root; adapt if your environment differs)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STORAGE_PATH = os.path.join(ROOT, "core_data")
POLICY_FILE = os.path.join(STORAGE_PATH, "access_control.json")
LOG_DIR = os.path.join(ROOT, "core", "logs")
LOG_FILE = os.path.join(LOG_DIR, "access_control.log")

# Ensure storage dirs exist
os.makedirs(STORAGE_PATH, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# PBKDF2 parameters
_PBKDF2_ITER = 200_000
_HASH_NAME = "sha256"
_SALT_BYTES = 16  # stored as hex


_lock = threading.RLock()


def _now_ts() -> float:
    return time.time()


def _iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _log(msg: str) -> None:
    ts = _iso_now()
    line = f"[{ts}] {msg}\n"
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)


def _hash_password(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    """
    Returns (salt_hex, hash_hex).
    If salt_hex is None, a new random salt is generated.
    """
    if salt_hex is None:
        salt = os.urandom(_SALT_BYTES)
        salt_hex = salt.hex()
    else:
        salt = bytes.fromhex(salt_hex)
    dk = pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, _PBKDF2_ITER)
    return salt_hex, dk.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    _, candidate = _hash_password(password, salt_hex)
    return candidate == hash_hex


@dataclass
class TempAccess:
    token: str
    agent_id: str
    subchat_id: str
    allowed_actions: List[str]  # e.g., ["read", "write"]
    expires_at: float  # epoch seconds

    def is_valid(self) -> bool:
        return _now_ts() < self.expires_at


class SubchatAccessControl:
    """
    File-backed Access Control service for subchats.

    Policies format (access_control.json):
    {
        "private_subchats": {
            "<subchat_id>": {
                "salt": "<hex>",
                "hash": "<hex>",
                "min_chars": 6,
                "pin_allowed": true
            },
            ...
        },
        "agent_policies": {
            "<agent_id>": {
                "allow_read