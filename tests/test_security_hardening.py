"""Focused tests for Phase 2 security hardening.

Covers:
- Bearer authentication and fail-closed validation
- Credential encryption with Fernet and removal of base64 fallback
- Outgoing webhook HMAC secret validation and signature format
- Startup security validation in production
- Simulation mode default
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import (
    INSECURE_BEARER_TOKENS,
    INSECURE_HMAC_SECRETS,
    compute_hmac_sha256,
    require_bearer_token,
    sign_job_callback,
    validate_security_settings,
    verify_hmac_sha256,
)
from app.core.settings import Settings
from app.services.credentials import (
    CredentialDecryptionError,
    CredentialEncryptionError,
    decrypt_credentials,
    encrypt_credentials,
    validate_credential_encryption_key,
)


# ── 1. Simulation Mode Safety Guard ───────────────────────────────────────────

def test_simulation_mode_enabled_by_default():
    """Verify that a fresh Settings instance defaults to simulation_mode=True."""
    settings = Settings(
        api_bearer_token="test-token-valid-16chars",
        credential_encryption_key=Fernet.generate_key().decode(),
        hmac_signing_secret="test-hmac-secret-16chars",
    )
    assert settings.simulation_mode is True, "Simulation mode must default to True for safety"


# ── 2. Bearer Authentication Tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bearer_token_missing_in_settings_rejects_with_401(monkeypatch):
    """When api_bearer_token is empty, require_bearer_token must reject all requests."""
    empty_token_settings = Settings(api_bearer_token="")
    import app.core.security as sec_module
    monkeypatch.setattr(sec_module, "get_settings", lambda: empty_token_settings)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")
    with pytest.raises(HTTPException) as exc_info:
        await require_bearer_token(creds)
    assert exc_info.value.status_code == 401
    assert "not securely configured" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bearer_token_insecure_default_rejects_with_401(monkeypatch):
    """When api_bearer_token uses known predictable default, require_bearer_token must reject."""
    for bad_token in INSECURE_BEARER_TOKENS:
        bad_settings = Settings(api_bearer_token=bad_token)
        import app.core.security as sec_module
        monkeypatch.setattr(sec_module, "get_settings", lambda: bad_settings)

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bad_token)
        with pytest.raises(HTTPException) as exc_info:
            await require_bearer_token(creds)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_bearer_token_valid_and_mismatched(monkeypatch):
    """Require_bearer_token accepts matching token and rejects mismatched token."""
    valid_token = "secure-production-bearer-token-12345"
    settings = Settings(api_bearer_token=valid_token)
    import app.core.security as sec_module
    monkeypatch.setattr(sec_module, "get_settings", lambda: settings)

    # Valid token succeeds
    valid_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=valid_token)
    result = await require_bearer_token(valid_creds)
    assert result == valid_token

    # Mismatched token fails with 401
    wrong_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-bearer-token")
    with pytest.raises(HTTPException) as exc_info:
        await require_bearer_token(wrong_creds)
    assert exc_info.value.status_code == 401
    assert "Invalid or missing" in exc_info.value.detail


# ── 3. Production Startup Fail-Closed Validation ──────────────────────────────

def test_production_fails_on_missing_or_insecure_api_token():
    valid_fernet = Fernet.generate_key().decode()
    valid_hmac = "valid-hmac-secret-min-16-chars"

    # Missing bearer token
    s1 = Settings(
        app_env="production",
        api_bearer_token="",
        credential_encryption_key=valid_fernet,
        hmac_signing_secret=valid_hmac,
    )
    with pytest.raises(RuntimeError, match="API_BEARER_TOKEN is required in production"):
        validate_security_settings(s1)

    # Insecure default bearer token
    s2 = Settings(
        app_env="production",
        api_bearer_token="change-me-local-dev-token",
        credential_encryption_key=valid_fernet,
        hmac_signing_secret=valid_hmac,
    )
    with pytest.raises(RuntimeError, match="insecure default"):
        validate_security_settings(s2)

    # Short bearer token
    s3 = Settings(
        app_env="production",
        api_bearer_token="short-tok",
        credential_encryption_key=valid_fernet,
        hmac_signing_secret=valid_hmac,
    )
    with pytest.raises(RuntimeError, match="at least 16 characters"):
        validate_security_settings(s3)


def test_production_fails_on_missing_or_insecure_hmac_secret():
    valid_fernet = Fernet.generate_key().decode()
    valid_token = "valid-bearer-token-at-least-16chars"

    # Missing HMAC secret
    s1 = Settings(
        app_env="production",
        api_bearer_token=valid_token,
        credential_encryption_key=valid_fernet,
        hmac_signing_secret="",
    )
    with pytest.raises(RuntimeError, match="HMAC_SIGNING_SECRET is required in production"):
        validate_security_settings(s1)

    # Insecure default HMAC secret
    s2 = Settings(
        app_env="production",
        api_bearer_token=valid_token,
        credential_encryption_key=valid_fernet,
        hmac_signing_secret="change-me-hmac-secret",
    )
    with pytest.raises(RuntimeError, match="insecure default"):
        validate_security_settings(s2)


def test_production_fails_on_missing_or_invalid_fernet_key():
    valid_token = "valid-bearer-token-at-least-16chars"
    valid_hmac = "valid-hmac-secret-min-16-chars"

    # Missing encryption key
    s1 = Settings(
        app_env="production",
        api_bearer_token=valid_token,
        credential_encryption_key="",
        hmac_signing_secret=valid_hmac,
    )
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEY is required in production"):
        validate_security_settings(s1)

    # Invalid Fernet key (not 32 base64 bytes)
    s2 = Settings(
        app_env="production",
        api_bearer_token=valid_token,
        credential_encryption_key="invalid-non-base64-key",
        hmac_signing_secret=valid_hmac,
    )
    with pytest.raises(RuntimeError, match="valid 32 url-safe base64-encoded bytes"):
        validate_security_settings(s2)


def test_production_succeeds_with_strong_configuration():
    valid_fernet = Fernet.generate_key().decode()
    valid_token = "strong-production-token-min-16-chars"
    valid_hmac = "strong-production-hmac-min-16-chars"

    settings = Settings(
        app_env="production",
        api_bearer_token=valid_token,
        credential_encryption_key=valid_fernet,
        hmac_signing_secret=valid_hmac,
    )
    # Should not raise
    validate_security_settings(settings)


# ── 4. Credential Encryption & Fernet Round-Trip Tests ────────────────────────

def test_missing_encryption_key_refuses_to_store_credentials(monkeypatch):
    """Encrypting without a key must refuse to store and NEVER output b64: fallback."""
    settings = Settings(credential_encryption_key="")
    import app.services.credentials as cred_module
    monkeypatch.setattr(cred_module, "get_settings", lambda: settings)

    with pytest.raises(CredentialEncryptionError, match="Refusing to store unencrypted credentials"):
        encrypt_credentials({"api_key": "secret-12345"})


def test_invalid_encryption_key_refuses_to_encrypt_or_decrypt(monkeypatch):
    """Malformed Fernet keys must be rejected safely."""
    settings = Settings(credential_encryption_key="malformed-not-valid-fernet-key")
    import app.services.credentials as cred_module
    monkeypatch.setattr(cred_module, "get_settings", lambda: settings)

    assert not validate_credential_encryption_key("malformed-not-valid-fernet-key")

    with pytest.raises(CredentialEncryptionError):
        encrypt_credentials({"api_key": "secret-12345"})

    with pytest.raises(CredentialDecryptionError):
        decrypt_credentials("some-ciphertext")


def test_successful_fernet_encryption_roundtrip(monkeypatch):
    """Valid Fernet key must encrypt/decrypt properly, and ciphertext must not leak plaintext."""
    real_key = Fernet.generate_key().decode()
    settings = Settings(credential_encryption_key=real_key)
    import app.services.credentials as cred_module
    monkeypatch.setattr(cred_module, "get_settings", lambda: settings)

    raw_creds = {
        "api_key": "super-secret-key-xyz",
        "api_username": "system-user",
        "nested": {"token": "sub-token-abc"},
    }

    encrypted = encrypt_credentials(raw_creds)

    # Must NOT use legacy b64 prefix
    assert not encrypted.startswith("b64:")
    # Must NOT contain plaintext secrets
    assert "super-secret-key-xyz" not in encrypted
    assert "system-user" not in encrypted

    # Must decrypt back to exact original dictionary
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == raw_creds


def test_legacy_base64_stored_credentials_decrypts_safely():
    """Ensure previously stored b64: records can still be read without error."""
    import base64
    import json

    legacy_payload = {"api_key": "legacy-key-123", "username": "legacy-user"}
    legacy_ciphertext = "b64:" + base64.b64encode(json.dumps(legacy_payload).encode()).decode()

    result = decrypt_credentials(legacy_ciphertext)
    assert result == legacy_payload


# ── 5. HMAC Signing & Verification Tests ──────────────────────────────────────

def test_hmac_signing_missing_secret_raises_error():
    """compute_hmac_sha256 and sign_job_callback must reject empty secret."""
    with pytest.raises(ValueError, match="HMAC signing secret must not be empty"):
        compute_hmac_sha256(b"payload", "")


def test_hmac_signing_and_verification_roundtrip():
    secret = "test-hmac-signing-key-12345"
    payload = b'{"action":"publish","status":"ok"}'

    # Bare hex signature
    sig_hex = compute_hmac_sha256(payload, secret)
    assert len(sig_hex) == 64
    assert verify_hmac_sha256(payload, secret, sig_hex) is True

    # Prefixed sha256= signature (standard in webhooks)
    sig_prefixed = f"sha256={sig_hex}"
    assert verify_hmac_sha256(payload, secret, sig_prefixed) is True

    # Tampered payload fails
    tampered_payload = b'{"action":"publish","status":"tampered"}'
    assert verify_hmac_sha256(tampered_payload, secret, sig_prefixed) is False

    # Tampered secret fails
    assert verify_hmac_sha256(payload, "wrong-secret", sig_prefixed) is False
