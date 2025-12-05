"""
captains_log_setup.py

Location:
  system/core/captains_log/captains_log_setup.py

Purpose:
- Initialize the encrypted Captain's Log vault structure:
    system/captains_log_vault/
      - vault_salt.bin
      - metadata.json.enc
      - vault_credentials.json.enc
      - entries/ (empty)
- Create KDF salt, derive key from provided password, create initial encrypted metadata and credentials.
- Safe CLI with password prompt (double-confirm).
- Options: --password (not recommended on shared machines), --force to overwrite existing vault.

Usage:
  python captains_log_setup.py       # will prompt for password
  python captains_log_setup.py --password "MySecret" --force
"""

import argparse
import json
import time
from pathlib import Path
import secrets
import getpass

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Paths (match captains_log module)
VAULT_DIR = Path("system/captains_log_vault")
SALT_FILE = VAULT_DIR / "vault_salt.bin"
METADATA_FILE = VAULT_DIR / "metadata.json.enc"
CREDENTIALS_FILE = VAULT_DIR / "vault_credentials.json.enc"
ENTRIES_DIR = VAULT_DIR / "entries"

# KDF params (must match captains_log)
KDF_ITERS = 200_000
KDF_LENGTH = 32  # bytes


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=KDF_LENGTH, salt=salt, iterations=KDF_ITERS)
    return kdf.derive(password.encode("utf-8"))


def encrypt_with_key(key: bytes, plaintext: bytes) -> bytes:
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aes.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def setup_vault(password: str, force: bool = False) -> None:
    # ensure directories
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)

    if SALT_FILE.exists() and not force:
        raise RuntimeError("Vault already exists. Use --force to reinitialize (will overwrite).")

    # create salt
    salt = secrets.token_bytes(16)
    SALT_FILE.write_bytes(salt)

    # derive key from password
    key = derive_key(password, salt)

    # initial empty metadata
    metadata = {}
    metadata_blob = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    enc_metadata = encrypt_with_key(key, metadata_blob)
    with open(METADATA_FILE, "wb") as f:
        f.write(enc_metadata)

    # create credentials blob (minimal info)
    credentials = {
        "created_at": int(time.time()),
        "version": "captains_log_v1"
    }
    cred_blob = json.dumps(credentials, ensure_ascii=False).encode("utf-8")
    enc_cred = encrypt_with_key(key, cred_blob)
    with open(CREDENTIALS_FILE, "wb") as f:
        f.write(enc_cred)

    print("Captain's Log vault initialized at:", str(VAULT_DIR.resolve()))
    print(" - Salt file:", str(SALT_FILE.name))
    print(" - Encrypted metadata:", str(METADATA_FILE.name))
    print(" - Encrypted credentials:", str(CREDENTIALS_FILE.name))
    print(" - Entries directory:", str(ENTRIES_DIR.name))


def _prompt_password(confirm: bool = True) -> str:
    while True:
        pw = getpass.getpass("Enter new vault password: ")
        if len(pw) < 6:
            print("Password too short (min 6 characters). Try again.")
            continue
        if confirm:
            pw2 = getpass.getpass("Confirm password: ")
            if pw != pw2:
                print("Passwords do not match. Try again.")
                continue
        return pw


def main():
    parser = argparse.ArgumentParser(description="Initialize Captain's Log encrypted vault.")
    parser.add_argument("--password", type=str, help="Initial vault password (unsafe on shared machines).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing vault if present.")
    args = parser.parse_args()

    if args.password:
        password = args.password
    else:
        password = _prompt_password(confirm=True)

    try:
        setup_vault(password=password, force=args.force)
    except Exception as e:
        print("ERROR:", e)


if __name__ == "__main__":
    main()