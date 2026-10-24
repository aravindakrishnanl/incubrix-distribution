"""Credential encryption/decryption service.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
The encryption key is loaded from CREDENTIAL_ENCRYPTION_KEY env var.

Key management notes:
  - Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  - Store the key in .env (never commit it)
  - Key rotation: re-encrypt all Connection.encrypted_credentials records
  - If the key is empty, credentials are stored as plaintext (dev/test only — not for production)
"""

from __future__ import annotations

import json
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.core.settings import get_settings


class CredentialEncryptionError(AppError, ValueError):
    """Raised when credential encryption fails or key is missing/invalid."""

    def __init__(self, message: str = "CREDENTIAL_ENCRYPTION_KEY is missing or invalid. Refusing to store unencrypted credentials."):
        super().__init__(ErrorCode.INTERNAL_ERROR, message)


class CredentialDecryptionError(AppError, ValueError):
    """Raised when credential decryption fails."""

    def __init__(self, message: str = "Failed to decrypt credentials. Encryption key is missing or invalid."):
        super().__init__(ErrorCode.INTERNAL_ERROR, message)


def validate_credential_encryption_key(key: str | bytes | None) -> bool:
    """Validate that key is a valid 32 url-safe base64-encoded bytes Fernet key."""
    if not key:
        return False
    try:
        from cryptography.fernet import Fernet
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        Fernet(key_bytes)
        return True
    except Exception:
        return False


def _get_fernet():
    settings = get_settings()
    key = settings.credential_encryption_key
    if not key or not validate_credential_encryption_key(key):
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_credentials(creds: dict[str, Any]) -> str:
    """Encrypt a credential dict to a storable Fernet ciphertext string.

    Refuses to store credentials if CREDENTIAL_ENCRYPTION_KEY is missing or invalid.
    Never falls back to unencrypted or base64 plaintext storage.
    """
    f = _get_fernet()
    if f is None:
        raise CredentialEncryptionError(
            "CREDENTIAL_ENCRYPTION_KEY is missing or invalid. Refusing to store unencrypted credentials."
        )
    raw = json.dumps(creds).encode("utf-8")
    return f.encrypt(raw).decode("utf-8")


def decrypt_credentials(encrypted: str) -> dict[str, Any]:
    """Decrypt a stored credential string back to a dict.

    Explicitly handles legacy 'b64:' encoded credentials to prevent data loss,
    while requiring a valid Fernet key for all Fernet-encrypted records.
    """
    if not encrypted:
        return {}

    # Backward compatibility: safely handle legacy base64-encoded records
    if encrypted.startswith("b64:"):
        import base64
        try:
            raw = base64.b64decode(encrypted[4:])
            return json.loads(raw)
        except Exception as exc:
            raise CredentialDecryptionError("Failed to decode legacy base64 credentials.") from exc

    f = _get_fernet()
    if f is None:
        raise CredentialDecryptionError(
            "CREDENTIAL_ENCRYPTION_KEY is missing or invalid; cannot decrypt Fernet-encrypted credentials."
        )
    try:
        raw = f.decrypt(encrypted.encode("utf-8"))
        return json.loads(raw)
    except Exception as exc:
        raise CredentialDecryptionError("Failed to decrypt credentials with configured encryption key.") from exc
