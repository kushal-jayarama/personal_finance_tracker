import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _derive_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    secret = settings.encryption_key or "change-this-in-production"
    return Fernet(_derive_key(secret))


def encrypt_text(text: str) -> str:
    return get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
