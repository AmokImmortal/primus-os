import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------
# Encrypt Data
# ---------------------------------------------------------
def encrypt_data(key: bytes, plaintext: str) -> dict:
    aes = AESGCM(key)
    nonce = os.urandom(12)
    encrypted = aes.encrypt(nonce, plaintext.encode("utf-8"), None)

    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(encrypted).decode()
    }


# ---------------------------------------------------------
# Decrypt Data
# ---------------------------------------------------------
def decrypt_data(key: bytes, payload: dict) -> str:
    aes = AESGCM(key)

    nonce = base64.b64decode(payload["nonce"])
    ciphertext = base64.b64decode(payload["ciphertext"])

    decrypted = aes.decrypt(nonce, ciphertext, None)
    return decrypted.decode("utf-8")
When you're ready, say "proceed with the next file".






