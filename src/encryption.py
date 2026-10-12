from cryptography.fernet import Fernet
from src.config import ENCRYPTION_KEY

_cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

def encrypt_secret(secret: str) -> str:
    """Encrypts a string secret into ciphertext string."""
    if not secret:
        return ""
    return _cipher.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypts a ciphertext string back into original string."""
    if not encrypted_secret:
        return ""
    try:
        return _cipher.decrypt(encrypted_secret.encode()).decode()
    except Exception:
        return ""
