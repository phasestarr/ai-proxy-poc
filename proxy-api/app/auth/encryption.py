from __future__ import annotations

from app.config.settings import settings


def encrypt_auth_payload(plaintext: bytes) -> bytes:
    return _build_auth_data_cipher().encrypt(plaintext)


def decrypt_auth_payload(ciphertext: bytes) -> bytes:
    return _build_auth_data_cipher().decrypt(ciphertext)


def _build_auth_data_cipher():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("cryptography is required for Microsoft auth flows") from exc

    if not settings.auth_data_encryption_key:
        raise RuntimeError("AUTH_DATA_ENCRYPTION_KEY is required for Microsoft auth flows")

    try:
        return Fernet(settings.auth_data_encryption_key.encode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("AUTH_DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc

