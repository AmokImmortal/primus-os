"""
Captain's Log - secure private vault access library

Location:
  system/core/captains_log/captains_log.py

Responsibilities:
- Manage encrypted vault of private entries under: system/captains_log_vault/
- Entries stored as individual encrypted files (nonce + ciphertext)
- Metadata stored encrypted (metadata.json.enc)
- Unlock/Lock using master password (PBKDF2-HMAC-SHA256 -> AES-GCM)
- Add / list / read / delete entries while unlocked
- Change password (requires current password)
- Minimal external dependencies: cryptography, json, pathlib, uuid, time

Usage pattern:
    from captains_log import CaptainsLog
    cl = CaptainsLog()
    cl.ensure_vault()
    cl.unlock("yourpassword")
    cl.add_entry("title", "text body")
    entries = cl.list_entries()
    content = cl.get_entry(entry_id)
    cl.lock()

Notes:
- This module intentionally avoids any external logging of entry contents.
- Keep master password safe. Changing password re-encrypts metadata + entries keys.
"""

import os
import json
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import secrets
import base64

# Vault paths (match captains_log_setup.py)
VAULT_DIR = Path("system/captains_log_vault")
SALT_FILE = VAULT_DIR / "vault_salt.bin"
CREDENTIAL_FILE = VAULT_DIR / "vault_credentials.json.enc"
ENTRY_DIR = VAULT_DIR / "entries"
METADATA_FILE = VAULT_DIR / "metadata.json.enc"

# KDF params (shared with setup)
KDF_ITERS = 200_000
KDF_LENGTH = 32  # bytes


class CaptainsLogError(Exception):
    pass


class CaptainsLog:
    def __init__(self):
        self.vault_dir = VAULT_DIR
        self.salt_file = SALT_FILE
        self.cred_file = CREDENTIAL_FILE
        self.entry_dir = ENTRY_DIR
        self.metadata_file = METADATA_FILE

        self._key: Optional[bytes] = None  # derived AES key when unlocked
        self._metadata: Dict[str, Dict[str, Any]] = {}  # id -> meta
        self._unlocked = False

    # -------------------------
    # Utilities / crypto
    # -------------------------
    def ensure_vault(self):
        """Create the vault structure if it doesn't exist (compatible with setup)."""
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.entry_dir.mkdir(parents=True, exist_ok=True)
        if not self.salt_file.exists():
            # create a salt if missing (only for convenience; normally created by setup)
            self.salt_file.write_bytes(secrets.token_bytes(16))

    def _derive_key(self, password: str) -> bytes:
        if not self.salt_file.exists():
            raise CaptainsLogError("Vault salt missing; run setup first.")
        salt = self.salt_file.read_bytes()
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=KDF_LENGTH, salt=salt, iterations=KDF_ITERS)
        return kdf.derive(password.encode("utf-8"))

    def _encrypt_bytes(self, key: bytes, plaintext: bytes) -> bytes:
        aes = AESGCM(key)
        nonce = secrets.token_bytes(12)
        ciphertext = aes.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def _decrypt_bytes(self, key: bytes, blob: bytes) -> bytes:
        aes = AESGCM(key)
        if len(blob) < 13:
            raise CaptainsLogError("Malformed encrypted blob.")
        nonce = blob[:12]
        ciphertext = blob[12:]
        return aes.decrypt(nonce, ciphertext, None)

    def _save_metadata(self):
        if not self._unlocked or self._key is None:
            raise CaptainsLogError("Vault is locked; cannot save metadata.")
        data = json.dumps(self._metadata, ensure_ascii=False).encode("utf-8")
        enc = self._encrypt_bytes(self._key, data)
        with open(self.metadata_file, "wb") as f:
            f.write(enc)

    def _load_metadata(self):
        if not self.metadata_file.exists():
            self._metadata = {}
            return
        blob = self.metadata_file.read_bytes()
        raw = self._decrypt_bytes(self._key, blob)
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, dict):
            self._metadata = obj
        else:
            self._metadata = {}

    # -------------------------
    # Unlock / Lock / Status
    # -------------------------
    def is_initialized(self) -> bool:
        return self.salt_file.exists() and self.cred_file.exists()

    def unlock(self, password: str) -> bool:
        """
        Unlocks the vault using the master password.
        Loads metadata into memory. Returns True on success.
        """
        self.ensure_vault()
        try:
            key = self._derive_key(password)
            # try loading metadata (if exists) using derived key
            if self.metadata_file.exists():
                # attempt decrypt to validate key
                blob = self.metadata_file.read_bytes()
                _ = self._decrypt_bytes(key, blob)  # may raise
                # success -> set key and load metadata
                self._key = key
                self._unlocked = True
                self._load_metadata()
                return True
            else:
                # no metadata yet; still accept key (first-time use)
                self._key = key
                self._unlocked = True
                self._metadata = {}
                return True
        except Exception as e:
            # invalid password or corrupt metadata -> fail
            raise CaptainsLogError("Unlock failed: invalid password or corrupt vault.") from e

    def lock(self):
        """Wipe sensitive material from memory and mark vault locked."""
        # zero references
        self._key = None
        self._metadata = {}
        self._unlocked = False

    # -------------------------
    # Entry operations
    # -------------------------
    def add_entry(self, title: str, content: str, tags: Optional[List[str]] = None) -> str:
        """
        Adds a new entry to the vault.
        Returns the entry id.
        """
        if not self._unlocked or self._key is None:
            raise CaptainsLogError("Vault locked. Unlock first.")

        entry_id = str(uuid.uuid4())
        timestamp = int(time.time())
        tags = tags or []

        # prepare metadata without content
        meta = {
            "id": entry_id,
            "title": title,
            "created_at": timestamp,
            "updated_at": timestamp,
            "tags": tags,
            "filename": f"{entry_id}.enc",
        }

        # encrypt content and write to file
        plaintext = content.encode("utf-8")
        enc_blob = self._encrypt_bytes(self._key, plaintext)
        path = self.entry_dir / meta["filename"]
        with open(path, "wb") as f:
            f.write(enc_blob)

        # update metadata store
        self._metadata[entry_id] = meta
        self._save_metadata()
        return entry_id

    def list_entries(self) -> List[Dict[str, Any]]:
        """Return shallow metadata list for all entries (no content)."""
        if not self._unlocked:
            raise CaptainsLogError("Vault locked. Unlock first.")
        return list(self._metadata.values())

    def get_entry(self, entry_id: str) -> Dict[str, Any]:
        """Return entry metadata + decrypted content."""
        if not self._unlocked or self._key is None:
            raise CaptainsLogError("Vault locked. Unlock first.")
        meta = self._metadata.get(entry_id)
        if not meta:
            raise CaptainsLogError("Entry not found.")
        file_path = self.entry_dir / meta["filename"]
        if not file_path.exists():
            raise CaptainsLogError("Entry file missing.")
        blob = file_path.read_bytes()
        try:
            plaintext = self._decrypt_bytes(self._key, blob)
        except Exception as e:
            raise CaptainsLogError("Failed to decrypt entry.") from e
        content = plaintext.decode("utf-8", errors="replace")
        out = dict(meta)
        out["content"] = content
        return out

    def delete_entry(self, entry_id: str) -> bool:
        """Permanently delete an entry (metadata + file)."""
        if not self._unlocked:
            raise CaptainsLogError("Vault locked. Unlock first.")
        meta = self._metadata.pop(entry_id, None)
        if meta:
            file_path = self.entry_dir / meta["filename"]
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass
            self._save_metadata()
            return True
        return False

    def update_entry(self, entry_id: str, title: Optional[str] = None, content: Optional[str] = None,
                     tags: Optional[List[str]] = None) -> bool:
        """Update metadata and/or content of an entry."""
        if not self._unlocked:
            raise CaptainsLogError("Vault locked. Unlock first.")
        meta = self._metadata.get(entry_id)
        if not meta:
            raise CaptainsLogError("Entry not found.")
        changed = False
        if title is not None:
            meta["title"] = title
            changed = True
        if tags is not None:
            meta["tags"] = tags
            changed = True
        if content is not None:
            # overwrite encrypted content file
            blob = self._encrypt_bytes(self._key, content.encode("utf-8"))
            path = self.entry_dir / meta["filename"]
            with open(path, "wb") as f:
                f.write(blob)
            changed = True
        if changed:
            meta["updated_at"] = int(time.time())
            self._metadata[entry_id] = meta
            self._save_metadata()
        return True

    # -------------------------
    # Password management
    # -------------------------
    def change_password(self, current_password: str, new_password: str):
        """
        Change master password. Requires current_password.
        This re-derives key from current_password, decrypts all data, then re-encrypts with new key.
        """
        # verify current password by deriving and attempting decrypt
        try:
            current_key = self._derive_key(current_password)
        except Exception:
            raise CaptainsLogError("Invalid current password.")

        # attempt to decrypt metadata with current_key
        if self.metadata_file.exists():
            blob = self.metadata_file.read_bytes()
            try:
                raw = self._decrypt_bytes(current_key, blob)
            except Exception:
                raise CaptainsLogError("Current password incorrect; cannot change password.")
        else:
            raw = json.dumps(self._metadata).encode("utf-8")

        # decrypt all entry files with current_key, re-encrypt with new_key
        new_key = self._derive_key(new_password)

        # decrypt each entry, then write re-encrypted file
        for eid, meta in list(self._metadata.items()):
            path = self.entry_dir / meta["filename"]
            if not path.exists():
                continue
            blob = path.read_bytes()
            try:
                plaintext = self._decrypt_bytes(current_key, blob)
            except Exception as e:
                raise CaptainsLogError(f"Failed to decrypt entry {eid} with current password.") from e
            # re-encrypt with new key
            new_blob = self._encrypt_bytes(new_key, plaintext)
            with open(path, "wb") as f:
                f.write(new_blob)

        # re-encrypt metadata with new key
        self._key = new_key
        self._unlocked = True
        self._save_metadata()

        # NOTE: credentials file re-encryption is handled by setup/change-credential functions externally.
        return True

    # -------------------------
    # Misc utilities
    # -------------------------
    def export_metadata_plain(self, dest: Path):
        """Export metadata in plain JSON (owner responsibility). Only allowed when unlocked."""
        if not self._unlocked:
            raise CaptainsLogError("Vault locked. Unlock first.")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, indent=2, ensure_ascii=False)

    # For future: implement recovery via PIN or security questions (requires separate protected storage).
    # Placeholder API:
    def supports_recovery(self) -> bool:
        """Indicates if recovery mechanisms are present (implementation external)."""
        return False





