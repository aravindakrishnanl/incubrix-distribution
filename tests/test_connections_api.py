"""Tests for Connections CRUD API and secure credential handling."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_connections_crud_and_credential_security(async_client):
    # 1. Create a connection with secret credentials
    create_payload = {
        "slug": "conn-discourse-main",
        "name": "Discourse Main Connection",
        "connector_key": "discourse",
        "base_url": "https://discourse.example.com",
        "credentials": {
            "api_key": "super-secret-api-key-12345",
            "api_username": "system_admin",
        },
        "rate_limit_per_minute": 60,
    }
    resp = await async_client.post("/api/v1/connections", json=create_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["slug"] == "conn-discourse-main"
    assert data["connector_key"] == "discourse"
    conn_id = data["id"]

    # CRITICAL: Credentials must NOT be exposed in plaintext in response
    assert "credentials" not in data or data.get("credentials") is None or "super-secret-api-key-12345" not in str(data)

    # 2. Get connection
    resp = await async_client.get(f"/api/v1/connections/{conn_id}")
    assert resp.status_code == 200
    conn_data = resp.json()
    assert conn_data["id"] == conn_id
    # Ensure credentials are not leaked in GET
    assert "super-secret-api-key-12345" not in str(conn_data)

    # 3. List connections
    resp = await async_client.get("/api/v1/connections", params={"connector_key": "discourse"})
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    assert any(c["id"] == conn_id for c in items)
    # Ensure no credentials leaked in list
    assert "super-secret-api-key-12345" not in str(items)

    # 4. Update connection
    update_payload = {"name": "Discourse Main Renamed", "rate_limit_per_minute": 120}
    resp = await async_client.patch(f"/api/v1/connections/{conn_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Discourse Main Renamed"
