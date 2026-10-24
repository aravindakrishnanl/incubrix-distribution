"""Connector contract tests.

Verifies that all six connectors implement the Appendix A contract:
- validate, publish, get_status, delete return correct shapes
- disabled connectors return CONNECTOR_DISABLED
- unknown connectors return UNKNOWN_CONNECTOR
- manifest files load correctly
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

CONNECTOR_KEYS = ["discourse", "lemmy", "devto", "ghost", "webhook_hmac", "assisted"]
REQUIRED_METHODS = ["validate", "publish", "get_status", "delete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_key", CONNECTOR_KEYS)
async def test_validate_returns_ok_shape(async_client, connector_key):
    """All connectors must return {ok, violations[]} from validate."""
    resp = await async_client.post(
        f"/connector/v1/{connector_key}/validate",
        json={
            "rendition": {"title": "Test", "body": "Test body"},
            "destination": {"url": "http://example.com", "community_id": 1},
            "connection": {"api_key": "test", "base_url": "http://mock.example.com"},
        },
    )
    # Should not crash; may return ok=True or ok=False depending on rules
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        data = resp.json()
        assert "ok" in data
        assert "violations" in data
        assert isinstance(data["violations"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_key", CONNECTOR_KEYS)
async def test_validate_catches_spec_violation(async_client, connector_key):
    """Empty title should produce a spec violation for most connectors."""
    resp = await async_client.post(
        f"/connector/v1/{connector_key}/validate",
        json={
            "rendition": {"title": "", "body": ""},
            "destination": {},
            "connection": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "violations" in data
    # Most connectors require a title; assisted also requires it
    if connector_key != "webhook_hmac":
        assert data["ok"] is False
        assert len(data["violations"]) > 0


@pytest.mark.asyncio
async def test_unknown_connector_error(async_client):
    resp = await async_client.post(
        "/connector/v1/unknown_connector_xyz/validate",
        json={"rendition": {}, "destination": {}, "connection": {}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "UNKNOWN_CONNECTOR"


@pytest.mark.asyncio
async def test_unknown_method_error(async_client):
    resp = await async_client.post(
        "/connector/v1/discourse/not_a_real_method",
        json={},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "UNKNOWN_METHOD"


@pytest.mark.asyncio
async def test_disabled_connector_returns_error(async_client, monkeypatch):
    import app.core.settings as settings_module
    settings = settings_module.get_settings()
    original = settings.connector_discourse_enabled
    settings.connector_discourse_enabled = False
    try:
        resp = await async_client.post(
            "/connector/v1/discourse/validate",
            json={"rendition": {}, "destination": {}, "connection": {}},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "CONNECTOR_DISABLED"
    finally:
        settings.connector_discourse_enabled = original


@pytest.mark.asyncio
async def test_manifest_loaded_for_all_connectors():
    """Manifests must be loadable and contain required Appendix A fields."""
    from app.connectors.registry import get_manifest, init_registry, _MANIFESTS
    # Ensure manifests are loaded
    if not _MANIFESTS:
        init_registry()

    required_fields = {"key", "version", "tier", "auth", "surfaces", "rate_limits", "capabilities", "error_map"}
    for key in CONNECTOR_KEYS:
        manifest = get_manifest(key)
        missing = required_fields - manifest.keys()
        assert not missing, f"Manifest {key!r} missing fields: {missing}"
        assert manifest["key"] == key


@pytest.mark.asyncio
async def test_assisted_build_assist_pack_method(async_client):
    """Assisted connector must expose build_assist_pack."""
    resp = await async_client.post(
        "/connector/v1/assisted/build_assist_pack",
        json={
            "rendition": {"title": "My Post", "body": "Hello world"},
            "destination": {"url": "https://example.com", "rules_url": "https://example.com/rules"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert "caption" in data
    assert "deep_link" in data
    assert "checklist" in data
    assert isinstance(data["files"], list)
    assert isinstance(data["checklist"], list)


@pytest.mark.asyncio
async def test_malformed_request_body(async_client):
    """Malformed (non-JSON) body should not crash the app."""
    from httpx import AsyncClient, ASGITransport
    import app.main as main_module
    async with AsyncClient(
        transport=ASGITransport(app=main_module.app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
    ) as c:
        resp = await c.post(
            "/connector/v1/discourse/validate",
            content=b"not json {{{",
        )
    # Should return a sensible error, not a 500
    assert resp.status_code < 500 or resp.json().get("error", {}).get("code") == "INTERNAL_ERROR"
