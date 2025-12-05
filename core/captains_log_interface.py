# captains_log_interface.py
"""
Captain's Log Interface - Sandbox mode controller for PRIMUS OS

Responsibilities:
- Manage entering/exiting "Captain's Log" sandbox mode (password-protected).
- Enforce sandbox isolation rules:
    * Sandbox is offline-only by default (functions that require internet must be explicitly allowed
      via `allow_internet_for_sandbox = True` — default False).
    * Sandbox writes/logging are disabled unless explicitly enabled by the user inside sandbox.
    * Sandbox may read PRIMUS personality for editing but cannot apply changes without explicit approval.
- Provide utilities for:
    * Loading/saving a sandbox-local personality JSON
    * Backup/restore sandbox files (checkpointing)
    * Read-only access to system RAG (configurable) and full read/write access only for sandbox RAG folder
    * Password reset using security questions (local only)
- Minimal external dependencies (standard library only).
- Safe-by-default: operations that could leak data or change system state require explicit approval.

Paths/config:
- SANDBOX_ROOT - local directory for Captain's Log files (personality copy, rag, backups).
- PERSONALITY_FILENAME - copy of the main personality used in sandbox.
- METADATA_FILENAME - stores password hash, salt, security Q&A, settings.
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
import secrets
import getpass
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# ----------------------------
# Configuration (adjustable)
# ----------------------------
SYSTEM_ROOT = Path(__file__).resolve().parents[1]  # assume .../System/core/.. adjust if needed
SANDBOX_ROOT = SYSTEM_ROOT / "captains_log"  # C:\P.R.I.M.U.S OS\System\captains_log
SANDBOX_RAG = SANDBOX_ROOT / "rag"
PERSONALITY_FILENAME = SANDBOX_ROOT / "personality_sandbox.json"
METADATA_FILENAME = SANDBOX_ROOT / "sandbox_meta.json"
BACKUP_DIR = SANDBOX_ROOT / "backups"

# Default sandbox policy flags (persisted into metadata)
DEFAULT_POLICY = {
    "allow_internet": False,       # Sandbox starts offline-only
    "allow_write_outside": False,  # Sandbox cannot write to system folders
    "allow_logging": False,        # No logging by default
    "max_auto_backups": 10
}

# ----------------------------
# Helper crypto functions
# ----------------------------
def _derive_hash(password: str, salt: bytes, iterations: int = 200_000) -> str:
    """Derive a password hash using PBKDF2-HMAC-SHA256 and return hex string."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()

def _generate_salt(length: int = 16) -> bytes:
    return secrets.token_bytes(length)

# ----------------------------
# Sandbox Metadata Management
# ----------------------------
def _ensure_sandbox_dirs():
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_RAG.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not METADATA_FILENAME.exists():
        meta = {
            "password_hash": None,
            "salt_hex": None,
            "security_questions": [],  # list of {"q": str, "a_hash": str}
            "policy": DEFAULT_POLICY.copy(),
        }
        _save_meta(meta)

def _load_meta() -> Dict[str, Any]:
    _ensure_sandbox_dirs()
    try:
        with open(METADATA_FILENAME, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        meta = {
            "password_hash": None,
            "salt_hex": None,
            "security_questions": [],
            "policy": DEFAULT_POLICY.copy(),
        }
        _save_meta(meta)
        return meta

def _save_meta(meta: Dict[str, Any]):
    _ensure_sandbox_dirs()
    with open(METADATA_FILENAME, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

# ----------------------------
# Captain's Log Interface Class
# ----------------------------
class CaptainsLogInterface:
    def __init__(self):
        _ensure_sandbox_dirs()
        self._meta = _load_meta()
        self._in_sandbox = False
        # runtime flags (not persisted unless saved to meta)
        self.runtime_policy = dict(self._meta.get("policy", DEFAULT_POLICY.copy()))

    # ------------------------
    # Password & Security
    # ------------------------
    def set_password(self, password: str, security_qas: Optional[List[Tuple[str, str]]] = None):
        """
        Initialize or update the sandbox password and optional security Q&As (list of (Q, A)).
        Stores password hash and salted security answers (hashed).
        """
        salt = _generate_salt()
        phash = _derive_hash(password, salt)
        self._meta["password_hash"] = phash
        self._meta["salt_hex"] = salt.hex()
        # store security Q&As hashed
        qas = []
        if security_qas:
            for q, a in security_qas:
                a_hash = _derive_hash(a, salt)
                qas.append({"q": q, "a_hash": a_hash})
        self._meta["security_questions"] = qas
        _save_meta(self._meta)

    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        salt_hex = self._meta.get("salt_hex")
        phash = self._meta.get("password_hash")
        if not salt_hex or not phash:
            return False
        salt = bytes.fromhex(salt_hex)
        return _derive_hash(password, salt) == phash

    def reset_password_via_security(self, answers: List[str], new_password: str) -> bool:
        """
        Reset password by answering the security questions in order.
        Returns True if successful.
        """
        qas = self._meta.get("security_questions", [])
        if len(qas) == 0 or len(answers) != len(qas):
            return False
        salt = bytes.fromhex(self._meta.get("salt_hex", "00"))
        for provided, qa in zip(answers, qas):
            if _derive_hash(provided, salt) != qa["a_hash"]:
                return False
        # all matched: set new password with fresh salt
        self.set_password(new_password, [(qa["q"], provided) for qa, provided in zip(qas, answers)])
        return True

    # ------------------------
    # Sandbox lifecycle
    # ------------------------
    def enter_sandbox(self, password: Optional[str] = None) -> bool:
        """
        Attempt to enter sandbox. If password is required, it must be provided.
        Returns True on success.
        """
        if self._meta.get("password_hash") is None:
            raise RuntimeError("Sandbox password is not set. Use set_password() first.")
        if password is None:
            # Try interactive prompt if available
            try:
                password = getpass.getpass("Captain's Log password: ")
            except Exception:
                raise RuntimeError("No password provided and no TTY available.")
        if not self.verify_password(password):
            return False
        # Reload meta and policy into runtime
        self._meta = _load_meta()
        self.runtime_policy = dict(self._meta.get("policy", DEFAULT_POLICY.copy()))
        self._in_sandbox = True
        return True

    def exit_sandbox(self):
        """Exit sandbox mode. Runtime flags are kept but sandbox-specific state cleared."""
        self._in_sandbox = False

    def is_in_sandbox(self) -> bool:
        return bool(self._in_sandbox)

    # ------------------------
    # Policy controls (runtime only until saved)
    # ------------------------
    def get_policy(self) -> Dict[str, Any]:
        return dict(self.runtime_policy)

    def set_policy(self, key: str, value: Any, persist: bool = False):
        """
        Modify a runtime policy option.
        If `persist` True, writes back to metadata so next session uses it.
        """
        if key not in DEFAULT_POLICY:
            raise KeyError(f"Unknown policy key: {key}")
        self.runtime_policy[key] = value
        if persist:
            self._meta["policy"] = dict(self.runtime_policy)
            _save_meta(self._meta)

    # ------------------------
    # Personality operations
    # ------------------------
    def load_personality(self) -> Optional[Dict[str, Any]]:
        """Load the sandbox personality JSON if present. Returns dict or None."""
        if not PERSONALITY_FILENAME.exists():
            return None
        try:
            with open(PERSONALITY_FILENAME, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_personality(self, personality: Dict[str, Any], require_approval: bool = True) -> Dict[str, Any]:
        """
        Save a personality into the sandbox copy.
        If require_approval True, this only stages the new personality in a .pending file and returns a token
        that must be approved via `apply_staged_personality` (to enforce manual approval workflow).
        """
        _ensure_sandbox_dirs()
        if require_approval:
            token = secrets.token_hex(16)
            staged_path = SANDBOX_ROOT / f"personality_pending_{token}.json"
            with open(staged_path, "w", encoding="utf-8") as f:
                json.dump(personality, f, indent=2, ensure_ascii=False)
            return {"status": "staged", "token": token, "path": str(staged_path)}
        else:
            with open(PERSONALITY_FILENAME, "w", encoding="utf-8") as f:
                json.dump(personality, f, indent=2, ensure_ascii=False)
            return {"status": "saved", "path": str(PERSONALITY_FILENAME)}

    def list_staged_personalities(self) -> List[str]:
        """Return list of staged pending file names (tokens)."""
        files = []
        for p in SANDBOX_ROOT.glob("personality_pending_*.json"):
            files.append(p.name)
        return files

    def apply_staged_personality(self, token_or_filename: str, approve: bool = True) -> Dict[str, Any]:
        """
        Apply or discard a staged personality.
        If approve True -> move staged into the live PERSONALITY_FILENAME.
        If approve False -> delete staged file.
        """
        staged_path = SANDBOX_ROOT / token_or_filename
        # allow direct token or filename
        if not staged_path.exists():
            # try token->filename
            staged_path = SANDBOX_ROOT / f"personality_pending_{token_or_filename}.json"
            if not staged_path.exists():
                return {"status": "error", "error": "staged_not_found"}
        if approve:
            shutil.move(str(staged_path), str(PERSONALITY_FILENAME))
            return {"status": "applied", "path": str(PERSONALITY_FILENAME)}
        else:
            staged_path.unlink(missing_ok=True)
            return {"status": "discarded"}

    # ------------------------
    # RAG access (sandbox-local and system read-only)
    # ------------------------
    def list_sandbox_rag(self) -> List[str]:
        """List files inside sandbox RAG folder."""
        _ensure_sandbox_dirs()
        return [str(p.relative_to(SANDBOX_RAG)) for p in SANDBOX_RAG.rglob("*") if p.is_file()]

    def read_sandbox_rag_file(self, relative_path: str) -> Optional[str]:
        """Read a file from sandbox RAG. Returns content or None."""
        path = (SANDBOX_RAG / relative_path).resolve()
        if not str(path).startswith(str(SANDBOX_RAG.resolve())):
            raise PermissionError("Access denied.")
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def write_sandbox_rag_file(self, relative_path: str, content: str, allow_overwrite: bool = True) -> Dict[str, Any]:
        """Write into sandbox RAG only. Respects runtime policy on writing outside system."""
        if not self._in_sandbox:
            return {"status": "error", "error": "not_in_sandbox"}
        path = (SANDBOX_RAG / relative_path).resolve()
        if not str(path).startswith(str(SANDBOX_RAG.resolve())):
            return {"status": "error", "error": "invalid_path"}
        if path.exists() and not allow_overwrite:
            return {"status": "error", "error": "exists"}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": str(path)}

    def read_system_rag_readonly(self, system_rag_path: Path) -> Optional[str]:
        """
        Read from a system/global RAG folder in read-only mode.
        This enforces that sandbox cannot write to system RAGs. system_rag_path must be within SYSTEM_ROOT/rag/*.
        """
        system_rag_path = Path(system_rag_path).resolve()
        allowed_root = (SYSTEM_ROOT / "rag").resolve()
        if not str(system_rag_path).startswith(str(allowed_root)):
            raise PermissionError("Can only read from system RAG directory.")
        # read if exists
        if not system_rag_path.exists():
            return None
        with open(system_rag_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # ------------------------
    # Backup / Restore
    # ------------------------
    def create_backup(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Create a timestamped backup (snapshot) of the sandbox folder (personality + rag)."""
        import datetime
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        label_s = f"_{label}" if label else ""
        target = BACKUP_DIR / f"backup_{ts}{label_s}.zip"
        # create archive from SANDBOX_ROOT contents
        shutil.make_archive(str(target.with_suffix("")), 'zip', root_dir=str(SANDBOX_ROOT))
        # cleanup old backups if exceeding max
        maxb = int(self.runtime_policy.get("max_auto_backups", 10))
        backups = sorted(BACKUP_DIR.glob("backup_*.zip"), key=os.path.getmtime, reverse=True)
        for b in backups[maxb:]:
            try:
                b.unlink()
            except Exception:
                pass
        return {"status": "ok", "path": str(target)}

    def list_backups(self) -> List[str]:
        return [str(p.name) for p in sorted(BACKUP_DIR.glob("backup_*.zip"), key=os.path.getmtime, reverse=True)]

    def restore_backup(self, backup_filename: str) -> Dict[str, Any]:
        """Restore a previously created backup (destructive to current sandbox)."""
        target = BACKUP_DIR / backup_filename
        if not target.exists():
            return {"status": "error", "error": "backup_not_found"}
        # remove current sandbox content first (careful)
        for item in SANDBOX_ROOT.iterdir():
            if item == BACKUP_DIR:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                pass
        # extract backup into SANDBOX_ROOT
        shutil.unpack_archive(str(target), str(SANDBOX_ROOT))
        return {"status": "ok"}

    # ------------------------
    # Logging controls (sandbox-local only)
    # ------------------------
    def set_logging(self, enabled: bool, persist: bool = False) -> Dict[str, Any]:
        """
        Enable or disable sandbox logging. If persist True the choice is saved to meta.
        Note: Sandbox logs (if enabled) are saved inside SANDBOX_ROOT/logs/.
        """
        self.runtime_policy["allow_logging"] = bool(enabled)
        if persist:
            self._meta["policy"] = dict(self.runtime_policy)
            _save_meta(self._meta)
        return {"status": "ok", "allow_logging": self.runtime_policy["allow_logging"]}

    def append_sandbox_log(self, message: str):
        """Append a message to sandbox log if logging enabled."""
        if not self.runtime_policy.get("allow_logging", False):
            return
        logs_dir = SANDBOX_ROOT / "logs"
        logs_dir.mkdir(exist_ok=True)
        from datetime import datetime
        entry = {"ts": datetime.utcnow().isoformat() + "Z", "msg": message}
        log_file = logs_dir / "captains_log.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ------------------------
    # Safety / Enforcement helpers
    # ------------------------
    def ensure_offline(self) -> bool:
        """
        Assert sandbox is offline. If runtime policy allows internet, returns True.
        If not allowed, this returns True but should be used by calling code to block network calls.
        This function cannot truly block networking at OS level; it provides a centralized check point.
        """
        return bool(self.runtime_policy.get("allow_internet", False))

    # ------------------------
    # Utility helpers
    # ------------------------
    def list_sandbox_files(self) -> List[str]:
        """List all files under SANDBOX_ROOT relative paths."""
        out = []
        for p in SANDBOX_ROOT.rglob("*"):
            if p.is_file():
                out.append(str(p.relative_to(SANDBOX_ROOT)))
        return out

# ----------------------------
# Module-level convenience
# ----------------------------
_global_interface: Optional[CaptainsLogInterface] = None

def get_captains_log_interface() -> CaptainsLogInterface:
    global _global_interface
    if _global_interface is None:
        _global_interface = CaptainsLogInterface()
    return _global_interface

# ----------------------------
# Quick self-test (only when run directly)
# ----------------------------
if __name__ == "__main__":
    cli = get_captains_log_interface()
    print("Captain's Log sandbox root:", SANDBOX_ROOT)
    print("Meta file:", METADATA_FILENAME)
    print("Personality file (sandbox):", PERSONALITY_FILENAME)
    print("Backups dir:", BACKUP_DIR)
    print("Existing staged personalities:", cli.list_staged_personalities())
    print("Existing backups:", cli.list_backups())
    print("Sandbox policy (runtime):", cli.get_policy())