import os
import json
from .captains_log_auth import load_auth_file
from .captains_log_crypto import encrypt_data, decrypt_data

VAULT_DIR = os.path.join("system", "captains_log_vault")


# ---------------------------------------------------------
# Ensure vault directory exists
# ---------------------------------------------------------
def ensure_vault():
    if not os.path.exists(VAULT_DIR):
        raise FileNotFoundError("Captain's Log vault not found. Run captains_log_setup.py first.")


# ---------------------------------------------------------
# Load key (via password)
# ---------------------------------------------------------
def load_key(password: str) -> bytes:
    auth = load_auth_file()
    if auth is None:
        raise ValueError("Captain's Log authentication not initialized.")

    return auth.verify_password(password)


# ---------------------------------------------------------
# Save entry
# ---------------------------------------------------------
def save_entry(password: str, title: str, content: str) -> str:
    ensure_vault()

    key = load_key(password)

    entry_data = {
        "title": title,
        "content": content
    }

    encrypted = encrypt_data(key, json.dumps(entry_data))

    filename = title.replace(" ", "_").lower() + ".clog"
    save_path = os.path.join(VAULT_DIR, filename)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(encrypted, f, indent=4)

    return filename


# ---------------------------------------------------------
# Load entry
# ---------------------------------------------------------
def load_entry(password: str, filename: str) -> dict:
    ensure_vault()

    key = load_key(password)

    path = os.path.join(VAULT_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError("Entry does not exist.")

    with open(path, "r", encoding="utf-8") as f:
        encrypted = json.load(f)

    decrypted = decrypt_data(key, encrypted)
    return json.loads(decrypted)


# ---------------------------------------------------------
# List entries
# ---------------------------------------------------------
def list_entries() -> list:
    ensure_vault()

    files = [f for f in os.listdir(VAULT_DIR) if f.endswith(".clog")]
    return files