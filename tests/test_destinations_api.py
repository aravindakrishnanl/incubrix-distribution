"""Tests for Destinations CRUD and Bulk Import API."""

from __future__ import annotations

import uuid
import pytest


@pytest.mark.asyncio
async def test_destinations_crud(async_client):
    uid = uuid.uuid4().hex[:8]
    slug = f"test-tech-discourse-{uid}"
    # 1. Create a destination
    create_payload = {
        "slug": slug,
        "name": f"Test Tech Discourse {uid}",
        "connector_key": "discourse",
        "category": "community",
        "tier": "tier_1",
        "governance_mode": "automated",

        "rules": [
            {
                "rule_type": "frequency_cap",
                "parameters": {"max_posts_per_day": 5},
                "enforcement": "reject",
            }
        ],
        "metadata_": {"forum": "technology"},
    }
    resp = await async_client.post("/api/v1/destinations", json=create_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["slug"] == slug
    assert data["connector_key"] == "discourse"
    dest_id = data["id"]

    # 2. Get destination
    resp = await async_client.get(f"/api/v1/destinations/{dest_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == dest_id

    # 3. List destinations
    resp = await async_client.get("/api/v1/destinations", params={"connector_key": "discourse"})
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    assert any(d["id"] == dest_id for d in items)

    # 4. Update destination
    update_payload = {"name": "Updated Tech Discourse", "status": "active"}
    resp = await async_client.patch(f"/api/v1/destinations/{dest_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Tech Discourse"

    # 5. Delete destination (soft-delete)
    resp = await async_client.delete(f"/api/v1/destinations/{dest_id}")
    assert resp.status_code in (200, 204)


    # 6. Verify deleted is inactive/archived
    resp = await async_client.get(f"/api/v1/destinations/{dest_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_destinations_bulk_import_json(async_client):
    u = uuid.uuid4().hex[:6]
    destinations = [
        {
            "slug": f"bulk-dest-1-{u}",
            "name": f"Bulk Dest 1 {u}",
            "connector_key": "lemmy",
            "category": "aggregator",
            "tier": "tier_1",
            "governance_mode": "automated",
        },
        {
            "slug": f"bulk-dest-2-{u}",
            "name": f"Bulk Dest 2 {u}",
            "connector_key": "ghost",
            "category": "blog",
            "tier": "tier_2",
            "governance_mode": "assisted",
        },
    ]
    resp = await async_client.post("/api/v1/destinations/bulk", json={"destinations": destinations})

    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["imported_count"] == 2
    assert result["error_count"] == 0
