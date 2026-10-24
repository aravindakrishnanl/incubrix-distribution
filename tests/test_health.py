"""Tests for /health and /ready endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_includes_correlation_id_in_response(async_client):
    resp = await async_client.get("/health", headers={"X-Correlation-Id": "test-corr-123"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-Id") == "test-corr-123"


@pytest.mark.asyncio
async def test_health_generates_correlation_id_if_missing(async_client):
    resp = await async_client.get("/health")
    assert "X-Correlation-Id" in resp.headers
    corr_id = resp.headers["X-Correlation-Id"]
    assert len(corr_id) == 36  # UUID4


@pytest.mark.asyncio
async def test_ready_returns_status(async_client):
    """Ready should return 200 or 503 with a structured body."""
    resp = await async_client.get("/ready")
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert data["status"] in ("ok", "degraded")
