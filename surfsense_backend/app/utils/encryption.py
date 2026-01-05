import base64
import hashlib
import os
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import String, TypeDecorator

from app.config import config


def get_encryption_key() -> bytes:
    """
    Derive a 32-byte URL-safe base64-encoded key from the application SECRET_KEY.
    """
    secret = config.SECRET_KEY
    if not secret:
        # Fallback for development only if SECRET_KEY is not set
        # In production, SECRET_KEY must be set
        if os.getenv("ENVIRONMENT", "development") == "production":
            raise ValueError("SECRET_KEY must be set in production")
        secret = "default-insecure-secret-key-for-dev"

    # SHA-256 hash ensures we have 32 bytes
    key = hashlib.sha256(secret.encode()).digest()
    # Base64 encode to make it URL-safe for Fernet
    return base64.urlsafe_b64encode(key)


_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_encryption_key())
    return _fernet


def encrypt_value(value: str) -> str:
    if not value:
        return value
    f = get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    if not value:
        return value
    try:
        f = get_fernet()
        return f.decrypt(value.encode()).decode()
    except Exception:
        # In case the value is not encrypted or key changed, return as is or handle error
        # For migration purposes, returning as is might be useful if mixed content,
        # but for security, strict failure or specific handling is better.
        # Here we assume all data using this type will be encrypted.
        # But for safety during transition, if decryption fails, we might return the value
        # assuming it wasn't encrypted yet (legacy data).
        return value


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that encrypts data before saving to DB
    and decrypts it when loading.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is not None:
            return encrypt_value(str(value))
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is not None:
            return decrypt_value(str(value))
        return value
