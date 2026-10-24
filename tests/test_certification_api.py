"""Tests for Connector Certification API."""

from __future__ import annotations

import uuid
import pytest


@pytest.mark.asyncio
async def test_certification_run_and_status(async_client):
    u = uuid.uuid4().hex[:8]
    # 1. Create a destination to certify
    create_payload = {
        "slug": f"cert-devto-dest-{u}",
        "name": f"Cert Devto Dest {u}",
        "connector_key": "devto",
        "category": "blog",
        "tier": "tier_1",
        "governance_mode": "automated",
        "rules": [],
    }

    resp = await async_client.post("/api/v1/destinations", json=create_payload)
    assert resp.status_code == 201
    dest_id = resp.json()["id"]

    # 2. Run certification for destination
    cert_payload = {
        "destination_id": dest_id,
        "connector_key": "devto",
        "target_level": "gold",
    }
    resp = await async_client.post("/api/v1/certification/run", json=cert_payload)
    assert resp.status_code == 200, resp.text
    run_data = resp.json()
    assert run_data["status"] == "passed"
    run_id = run_data["run_id"]

    # 3. Get certification run details
    resp = await async_client.get(f"/api/v1/certification/{run_id}")
    assert resp.status_code == 200
    details = resp.json()
    assert details["run_id"] == run_id
    assert details["status"] == "passed"
    assert "summary" in details
    assert len(details.get("test_results", [])) > 0
