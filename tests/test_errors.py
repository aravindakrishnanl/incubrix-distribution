"""Tests for canonical error codes and error envelope format."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_unknown_connector_returns_404_envelope(async_client):
    resp = await async_client.post(
        "/connector/v1/nonexistent_connector/validate",
        json={"rendition": {}, "destination": {}, "connection": {}},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "UNKNOWN_CONNECTOR"
    assert "retryable" in data["error"]
    assert "message" in data["error"]
    assert "details" in data["error"]


@pytest.mark.asyncio
async def test_unknown_method_returns_404_envelope(async_client):
    resp = await async_client.post(
        "/connector/v1/discourse/nonexistent_method",
        json={},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "UNKNOWN_METHOD"


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401(async_client):
    from httpx import AsyncClient, ASGITransport
    import app.main as main_module
    async with AsyncClient(
        transport=ASGITransport(app=main_module.app),
        base_url="http://test",
    ) as unauthenticated_client:
        resp = await unauthenticated_client.post("/connector/v1/discourse/validate", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_error_envelope_no_stack_trace(async_client):
    """Error responses must not contain stack traces."""
    resp = await async_client.post(
        "/connector/v1/nonexistent/validate",
        json={},
    )
    body = resp.text
    assert "Traceback" not in body
    assert "traceback" not in body.lower()
    assert "line " not in body.lower()
