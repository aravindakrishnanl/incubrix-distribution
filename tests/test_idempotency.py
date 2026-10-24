"""Idempotency tests.

Tests:
  - Same key + same payload → same job_id returned
  - Same key + different payload → IDEMPOTENCY_CONFLICT
  - Fingerprint computation is deterministic
  - Idempotency records are stored in the database
"""

from __future__ import annotations

import pytest

from app.api.routes.jobs import _fingerprint


def test_fingerprint_deterministic():
    body = {"rendition": {"title": "Hello"}, "connector_key": "devto"}
    fp1 = _fingerprint("key-001", body)
    fp2 = _fingerprint("key-001", body)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_differs_on_payload_change():
    fp1 = _fingerprint("key-001", {"a": 1})
    fp2 = _fingerprint("key-001", {"a": 2})
    assert fp1 != fp2


def test_fingerprint_differs_on_key_change():
    fp1 = _fingerprint("key-001", {"a": 1})
    fp2 = _fingerprint("key-002", {"a": 1})
    assert fp1 != fp2


@pytest.mark.asyncio
async def test_same_key_same_payload_returns_same_job(async_client):
    """Submitting the same idempotency key twice returns the same job_id."""
    payload = {
        "connector_key": "assisted",
        "rendition": {"title": "Idempotency test", "body": "Body text"},
        "destination": {"url": "http://example.com"},
        "connection": {},
    }
    headers = {"Idempotency-Key": "idem-test-001"}

    resp1 = await async_client.post("/api/v1/publish", json=payload, headers=headers)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]

    resp2 = await async_client.post("/api/v1/publish", json=payload, headers=headers)
    assert resp2.status_code == 202
    job_id_2 = resp2.json()["job_id"]

    assert job_id_1 == job_id_2, "Same idempotency key must return same job_id"


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_conflict(async_client):
    """Different payload with same key must return IDEMPOTENCY_CONFLICT."""
    payload_a = {
        "connector_key": "assisted",
        "rendition": {"title": "Post A"},
        "destination": {},
        "connection": {},
    }
    payload_b = {
        "connector_key": "assisted",
        "rendition": {"title": "Post B — different"},
        "destination": {},
        "connection": {},
    }
    headers = {"Idempotency-Key": "idem-conflict-test-unique-001"}

    resp1 = await async_client.post("/api/v1/publish", json=payload_a, headers=headers)
    assert resp1.status_code == 202

    resp2 = await async_client.post("/api/v1/publish", json=payload_b, headers=headers)
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_missing_idempotency_key_returns_400(async_client):
    resp = await async_client.post(
        "/api/v1/publish",
        json={"connector_key": "assisted", "rendition": {"title": "Test"}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_job_returns_correct_structure(async_client):
    payload = {
        "connector_key": "assisted",
        "rendition": {"title": "Job structure test", "body": "body"},
        "destination": {"url": "http://example.com"},
        "connection": {},
    }
    headers = {"Idempotency-Key": "job-struct-test-001"}
    create_resp = await async_client.post("/api/v1/publish", json=payload, headers=headers)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    get_resp = await async_client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "job_id" in data
    assert data["job_id"] == job_id
    assert "status" in data
    assert data["status"] in ("queued", "running", "succeeded", "failed")
    assert "progress" in data
    assert 0 <= data["progress"] <= 100


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(async_client):
    resp = await async_client.get("/api/v1/jobs/nonexistent-job-id-xyz")
    assert resp.status_code == 404
