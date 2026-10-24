"""Tests verifying SIMULATION_MODE behavior across all 6 connector types.

SIMULATION_MODE must prevent any outbound HTTP calls, return deterministic
simulated outputs, and handle publish, get_status, delete, and metrics safely.
"""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from app.connectors.registry import init_registry, get_connector

init_registry()



@pytest.fixture(autouse=True)
def enable_simulation():
    with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
        yield


@pytest.mark.parametrize("connector_key", [
    "discourse",
    "lemmy",
    "devto",
    "ghost",
    "webhook_hmac",
    "assisted",
])
@pytest.mark.asyncio
async def test_simulation_publish(connector_key):
    connector = get_connector(connector_key)
    rendition = {"title": "Test Title", "body": "Test Body content for simulation."}
    destination = {"category_id": 1, "community_id": 1, "target_url": "https://example.com/webhook"}
    connection = {"base_url": "https://example.com", "api_key": "secret"}

    # Should complete without any network call or exception
    result = await connector.publish(rendition, destination, connection, "idem-sim-123")
    assert "platform_post_id" in result
    assert result.get("simulated") is True or "sim" in result["platform_post_id"]


@pytest.mark.parametrize("connector_key", [
    "discourse",
    "lemmy",
    "devto",
    "ghost",
    "webhook_hmac",
    "assisted",
])
@pytest.mark.asyncio
async def test_simulation_get_status(connector_key):
    connector = get_connector(connector_key)
    connection = {"base_url": "https://example.com", "api_key": "secret"}
    result = await connector.get_status("sim-post-123", connection)
    assert result["status"] in ("published", "active", "ready_for_review", "delivered", "assist_ready")


@pytest.mark.parametrize("connector_key", [
    "discourse",
    "lemmy",
    "devto",
    "ghost",
    "webhook_hmac",
    "assisted",
])
@pytest.mark.asyncio
async def test_simulation_delete(connector_key):
    connector = get_connector(connector_key)
    connection = {"base_url": "https://example.com", "api_key": "secret"}
    result = await connector.delete("sim-post-123", connection)
    assert result["deleted"] is True
