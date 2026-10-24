"""Security utilities: bearer token auth, HMAC signing, credential encryption."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)

INSECURE_BEARER_TOKENS: frozenset[str] = frozenset({
    "change-me-local-dev-token",
    "change-me",
    "dev-token",
    "token",
    "admin",
    "secret",
    "default",
    "password",
})

INSECURE_HMAC_SECRETS: frozenset[str] = frozenset({
    "change-me-hmac-secret",
    "change-me",
    "dev-signing-secret",
    "secret",
    "default",
    "password",
})


def validate_security_settings(settings: Settings) -> None:
    """Validate security settings at application startup.

    Fails closed (raises RuntimeError) when running in production with
    missing, predictable, or weak credentials. In non-production, logs
    actionable security warnings.
    """
    env = (settings.app_env or "").strip().lower()
    is_production = env in ("production", "prod")

    if is_production:
        errors: list[str] = []

        # 1. Bearer token
        token = settings.api_bearer_token
        if not token:
            errors.append("API_BEARER_TOKEN is required in production.")
        elif token in INSECURE_BEARER_TOKENS:
            errors.append("API_BEARER_TOKEN cannot use an insecure default in production.")
        elif len(token) < 16:
            errors.append("API_BEARER_TOKEN must be at least 16 characters in production.")

        # 2. HMAC signing secret
        hmac_sec = settings.hmac_signing_secret
        if not hmac_sec:
            errors.append("HMAC_SIGNING_SECRET is required in production.")
        elif hmac_sec in INSECURE_HMAC_SECRETS:
            errors.append("HMAC_SIGNING_SECRET cannot use an insecure default in production.")
        elif len(hmac_sec) < 16:
            errors.append("HMAC_SIGNING_SECRET must be at least 16 characters in production.")

        # 3. Credential encryption key
        from app.services.credentials import validate_credential_encryption_key
        key = settings.credential_encryption_key
        if not key:
            errors.append("CREDENTIAL_ENCRYPTION_KEY is required in production.")
        elif not validate_credential_encryption_key(key):
            errors.append("CREDENTIAL_ENCRYPTION_KEY must be a valid 32 url-safe base64-encoded bytes Fernet key.")

        if errors:
            raise RuntimeError(
                "Production startup failed due to security configuration violations:\n"
                + "\n".join(f"  - {err}" for err in errors)
            )


async def require_bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ] = None,
) -> str:
    """FastAPI dependency: validate the API bearer token.

    Returns the validated token value on success.
    Raises HTTP 401 on missing, insecure, or invalid token.
    Uses constant-time comparison to prevent timing side-channel attacks.
    """
    settings = get_settings()
    expected = settings.api_bearer_token

    if not expected or expected in INSECURE_BEARER_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API bearer token is not securely configured.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not credentials or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def compute_hmac_sha256(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a payload.

    Used for webhook connector signing and job callback signing.
    """
    if not secret:
        raise ValueError("HMAC signing secret must not be empty.")
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_hmac_sha256(payload: bytes, secret: str, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature in constant time.

    Supports both bare hexadecimal string and 'sha256=' prefixed format.
    """
    if not secret or not signature:
        return False
    expected = compute_hmac_sha256(payload, secret)
    target = signature.removeprefix("sha256=") if signature.startswith("sha256=") else signature
    return hmac.compare_digest(expected, target)


def sign_job_callback(job_id: str, event: str, payload: dict) -> str:
    """Create the X-IncuBrix-Signature header value for a job callback.

    Format: sha256={hex_signature}
    The signed payload is: {job_id}.{event}.{json_body_bytes}
    """
    settings = get_settings()
    if not settings.hmac_signing_secret:
        raise ValueError("HMAC_SIGNING_SECRET is not configured.")
    body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signed_data = f"{job_id}.{event}.".encode() + body_bytes
    sig = compute_hmac_sha256(signed_data, settings.hmac_signing_secret)
    return f"sha256={sig}"
