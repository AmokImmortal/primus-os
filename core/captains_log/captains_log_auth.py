import os
import json
import base64
import hashlib
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VAULT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "captains_log_vault")
AUTH_FILE = os.path.join(VAULT_ROOT, "vault_auth.json")


# ---------------------------------------------------------
# Utility: Derive AES-GCM Key from Password
# ---------------------------------------------------------
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashlib.sha256,
        length=32,
        salt=salt,
        iterations=200000,
    )
    return kdf.derive(password.encode("utf-8"))


# ---------------------------------------------------------
# Utility: Generate New Salt
# ---------------------------------------------------------
def new_salt() -> bytes:
    return os.urandom(16)


# ---------------------------------------------------------
# Initialize / Update Authentication Settings
# ---------------------------------------------------------
def initialize_auth(password: str, sec_qas: dict):
    """Creates or overwrites vault authentication credentials."""
    if not os.path.exists(VAULT_ROOT):
        raise RuntimeError("Captain’s Log vault does not exist. Run captains_log_setup.py first.")

    salt = new_salt()
    key = derive_key(password, salt)
    hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()

    auth_data = {
        "salt": base64.b64encode(salt).decode(),
        "password_hash": hashed,
        "security_questions": sec_qas
    }

    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth_data, f, indent=4)

    return True


# ---------------------------------------------------------
# Verify Password
# ---------------------------------------------------------
def verify_password(password: str) -> bool:
    if not os.path.exists(AUTH_FILE):
        return False

    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    stored_hash = data["password_hash"]
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash


# ---------------------------------------------------------
# Get AES Key (only after password validated)
# ---------------------------------------------------------
def get_vault_key(password: str) -> bytes:
    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    salt = base64.b64decode(data["salt"])
    return derive_key(password, salt)


# ---------------------------------------------------------
# Validate Security Questions
# ---------------------------------------------------------
def verify_security_answers(answers: dict) -> bool:
    if not os.path.exists(AUTH_FILE):
        return False

    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    stored = data["security_questions"]

    for key, val in answers.items():
        if key not in stored:
            return False
        if stored[key].strip().lower() != val.strip().lower():
            return False

    return True