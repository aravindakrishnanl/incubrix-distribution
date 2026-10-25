"""Tests for the IncuBrix Unified Publishing CLI (app.cli)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from app.cli.main import async_cli_entrypoint, cli_entrypoint
from app.cli.publisher import (
    DestinationInfo,
    JobResult,
    SUPPORTED_CONNECTORS,
    execute_batch,
    fetch_destinations,
    parse_and_validate_content,
    plan_batch,
)


@pytest.fixture
def sample_content_file(tmp_path: Path) -> Path:
    file = tmp_path / "content.json"
    content = {
        "title": "Unified Publishing Test Article",
        "body": "This is a cross-platform test publication body.",
        "tags": ["python", "cli", "distribution"],
        "ai_disclosed": True,
        "is_promotional": False,
    }
    file.write_text(json.dumps(content), encoding="utf-8")
    return file


@pytest.fixture
def sample_destinations_api_response() -> dict:
    return {
        "items": [
            {
                "id": "dest-discourse-1",
                "name": "Dev Forum",
                "connector_key": "discourse",
                "url": "https://forum.example.com",
                "active": True,
            },
            {
                "id": "dest-webhook-2",
                "name": "Partner Webhook",
                "connector_key": "webhook_hmac",
                "url": "https://webhook.site/test",
                "active": True,
            },
            {
                "id": "dest-assisted-3",
                "name": "Subreddit Technology",
                "connector_key": "assisted",
                "url": "https://reddit.com/r/technology/submit",
                "active": True,
            },
            {
                "id": "dest-inactive-4",
                "name": "Archived Blog",
                "connector_key": "ghost",
                "url": "https://blog.example.com",
                "active": False,
            },
        ],
        "total": 4,
    }


# ── 1. Content Parsing & Validation Tests ────────────────────────────────────

def test_parse_and_validate_content_success(sample_content_file):
    rendition = parse_and_validate_content(sample_content_file)
    assert rendition["title"] == "Unified Publishing Test Article"
    assert rendition["body"] == "This is a cross-platform test publication body."


def test_parse_and_validate_nested_rendition(tmp_path):
    nested_file = tmp_path / "nested.json"
    nested_file.write_text(
        json.dumps({"rendition": {"title": "Nested Title", "body": "Nested Body"}}),
        encoding="utf-8",
    )
    rendition = parse_and_validate_content(nested_file)
    assert rendition["title"] == "Nested Title"


def test_parse_and_validate_missing_title(tmp_path):
    invalid_file = tmp_path / "no_title.json"
    invalid_file.write_text(json.dumps({"body": "No title here"}), encoding="utf-8")
    with pytest.raises(ValueError, match="title"):
        parse_and_validate_content(invalid_file)


def test_parse_and_validate_nonexistent_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_and_validate_content(tmp_path / "nonexistent.json")


# ── 2. Dry-Run Mode Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_makes_no_publish_requests(sample_content_file, sample_destinations_api_response):
    mock_get = MagicMock()
    mock_get.return_value = MagicMock(
        status_code=200,
        is_success=True,
        json=MagicMock(return_value=sample_destinations_api_response),
    )

    mock_post = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):

        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "all",
            "--dry-run",
            "--token", "test-token",
        ])

        assert code == 0
        # Assert destinations were fetched
        mock_get.assert_called_once()
        # Assert NO publish jobs were submitted
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_default_mode_is_dry_run_without_live_flag(sample_content_file, sample_destinations_api_response):
    mock_get = MagicMock(
        return_value=MagicMock(
            status_code=200,
            is_success=True,
            json=MagicMock(return_value=sample_destinations_api_response),
        )
    )
    mock_post = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):

        # Neither --live nor --dry-run specified
        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "all",
            "--token", "test-token",
        ])

        assert code == 0
        # Crucial safety guard: must NOT have submitted any publish requests
        mock_post.assert_not_called()


def test_live_and_dry_run_mutually_exclusive(sample_content_file):
    code = cli_entrypoint([
        "publish",
        "--input", str(sample_content_file),
        "--destinations", "all",
        "--live",
        "--dry-run",
        "--token", "test-token",
    ])
    assert code == 1


# ── 3. Destination Discovery and Selection Tests ─────────────────────────────

@pytest.mark.asyncio
async def test_destinations_all_filters_only_active(sample_destinations_api_response):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = MagicMock(
        status_code=200,
        is_success=True,
        json=MagicMock(return_value=sample_destinations_api_response),
    )

    dests = await fetch_destinations(mock_client, ["all"])
    # 4 total in response, but only 3 are active (active=True)
    assert len(dests) == 3
    assert all(d.active for d in dests)
    assert "dest-inactive-4" not in [d.id for d in dests]


@pytest.mark.asyncio
async def test_explicit_destination_selection(sample_destinations_api_response):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = MagicMock(
        status_code=200,
        is_success=True,
        json=MagicMock(return_value=sample_destinations_api_response),
    )

    # User passes two IDs explicitly (comma-separated)
    dests = await fetch_destinations(mock_client, ["dest-discourse-1,dest-assisted-3"])
    assert len(dests) == 2
    ids = [d.id for d in dests]
    assert "dest-discourse-1" in ids
    assert "dest-assisted-3" in ids
    assert "dest-webhook-2" not in ids


@pytest.mark.asyncio
async def test_explicit_destination_not_found(sample_destinations_api_response):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # First call: list destinations (returns 4 items)
    mock_client.get.side_effect = [
        MagicMock(status_code=200, is_success=True, json=MagicMock(return_value=sample_destinations_api_response)),
        # Second call: try direct get for non-existent ID (returns 404)
        MagicMock(status_code=404, is_success=False),
    ]

    with pytest.raises(ValueError, match="not found in the catalogue"):
        await fetch_destinations(mock_client, ["missing-dest-999"])


# ── 4. Idempotency Key & Job Submission Tests ────────────────────────────────

def test_distinct_idempotency_keys_per_destination():
    d1 = DestinationInfo(id="id-1", name="D1", connector_key="discourse")
    d2 = DestinationInfo(id="id-2", name="D2", connector_key="ghost")
    plan = plan_batch([d1, d2], {"title": "Test Title"}, "batch-test-100")

    assert len(plan) == 2
    assert plan[0].idempotency_key != plan[1].idempotency_key
    assert plan[0].idempotency_key == "batch-test-100-id-1"
    assert plan[1].idempotency_key == "batch-test-100-id-2"


@pytest.mark.asyncio
async def test_live_publish_submits_distinct_jobs_and_keys():
    d1 = DestinationInfo(id="dest-1", name="D1", connector_key="discourse")
    d2 = DestinationInfo(id="dest-2", name="D2", connector_key="lemmy")
    plan = plan_batch([d1, d2], {"title": "Title"}, "batch-test-200")

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Mock POST /publish
    def mock_post(url, json=None, headers=None):
        dest_id = json["destination_id"]
        return MagicMock(status_code=202, is_success=True, json=MagicMock(return_value={"job_id": f"job-{dest_id}"}))

    # Mock GET /jobs/{job_id}
    def mock_get(url):
        return MagicMock(
            status_code=200,
            is_success=True,
            json=MagicMock(
                return_value={
                    "status": "succeeded",
                    "progress": 100,
                    "result": {"live_url": f"https://example.com/{url.split('/')[-1]}", "platform_post_id": "123"},
                }
            ),
        )

    mock_client.post.side_effect = mock_post
    mock_client.get.side_effect = mock_get

    report = await execute_batch(mock_client, plan, {"title": "Title"}, poll_interval=0.01, timeout_seconds=2.0)

    assert report.total_count == 2
    assert report.succeeded_count == 2
    assert report.failed_count == 0

    # Verify POST calls
    assert mock_client.post.call_count == 2
    calls = mock_client.post.call_args_list
    headers1 = calls[0].kwargs["headers"]
    headers2 = calls[1].kwargs["headers"]
    assert headers1["Idempotency-Key"] != headers2["Idempotency-Key"]
    assert "batch-test-200-dest-1" == headers1["Idempotency-Key"]
    assert "batch-test-200-dest-2" == headers2["Idempotency-Key"]


# ── 5. Multiple Job Polling & Aggregation Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_polling_and_aggregation_success(sample_content_file, sample_destinations_api_response):
    active_dests = [d for d in sample_destinations_api_response["items"] if d["active"]]

    def mock_get_handler(url, params=None):
        if "/api/v1/destinations" in url:
            return MagicMock(status_code=200, is_success=True, json=MagicMock(return_value=sample_destinations_api_response))
        if "/api/v1/jobs/" in url:
            jid = url.split("/")[-1]
            return MagicMock(
                status_code=200,
                is_success=True,
                json=MagicMock(
                    return_value={
                        "status": "succeeded",
                        "progress": 100,
                        "result": {"live_url": f"https://pub.example.com/{jid}", "platform_post_id": f"pid-{jid}"},
                    }
                ),
            )
        return MagicMock(status_code=404, is_success=False)

    def mock_post_handler(url, json=None, headers=None):
        dest_id = json.get("destination_id")
        return MagicMock(status_code=202, is_success=True, json=MagicMock(return_value={"job_id": f"job-for-{dest_id}"}))

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get_handler)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post_handler)):

        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "all",
            "--live",
            "--token", "valid-token",
            "--poll-interval", "0.01",
            "--timeout", "5.0",
        ])

        assert code == 0


# ── 6. Partial Failure Handling ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_failure_does_not_mask_success(sample_content_file, sample_destinations_api_response):
    # Only test 2 destinations: discourse (succeeds) and webhook (fails)
    two_dests = {
        "items": [
            sample_destinations_api_response["items"][0],  # discourse
            sample_destinations_api_response["items"][1],  # webhook
        ],
        "total": 2,
    }

    def mock_get_handler(url, params=None):
        if "/api/v1/destinations" in url:
            return MagicMock(status_code=200, is_success=True, json=MagicMock(return_value=two_dests))
        if "/api/v1/jobs/job-dest-discourse-1" in url:
            return MagicMock(
                status_code=200,
                is_success=True,
                json=MagicMock(
                    return_value={
                        "status": "succeeded",
                        "progress": 100,
                        "result": {"live_url": "https://forum.example.com/t/999", "platform_post_id": "999"},
                    }
                ),
            )
        if "/api/v1/jobs/job-dest-webhook-2" in url:
            return MagicMock(
                status_code=200,
                is_success=True,
                json=MagicMock(
                    return_value={
                        "status": "failed",
                        "progress": 0,
                        "error": {"code": "PLATFORM_UNAVAILABLE", "message": "Partner server returned 503"},
                    }
                ),
            )
        return MagicMock(status_code=404)

    def mock_post_handler(url, json=None, headers=None):
        dest_id = json.get("destination_id")
        return MagicMock(status_code=202, is_success=True, json=MagicMock(return_value={"job_id": f"job-{dest_id}"}))

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get_handler)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post_handler)):

        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "dest-discourse-1,dest-webhook-2",
            "--live",
            "--token", "valid-token",
            "--poll-interval", "0.01",
        ])

        # Must exit non-zero because one destination failed
        assert code == 1


# ── 7. Assisted Publishing and Webhook Result Formatting ─────────────────────

def test_assisted_and_webhook_representation():
    # Assisted publishing
    dest_assisted = DestinationInfo(id="ast-1", name="Manual Submission", connector_key="assisted", url="https://example.com/submit")
    res_assisted = JobResult(
        destination=dest_assisted,
        idempotency_key="key-1",
        job_id="job-ast",
        status="succeeded",
        live_url="https://example.com/submit",
    )
    assert res_assisted.display_status == "assist_ready"
    assert "Assisted Pack Ready" in res_assisted.formatted_reference
    assert "Human post required" in res_assisted.formatted_reference

    # Webhook delivery
    dest_webhook = DestinationInfo(id="wh-1", name="Partner Hook", connector_key="webhook_hmac", url="https://webhook.site/abc")
    res_webhook = JobResult(
        destination=dest_webhook,
        idempotency_key="key-2",
        job_id="job-wh",
        status="succeeded",
        live_url="https://webhook.site/abc",
    )
    assert res_webhook.display_status == "delivered"
    assert "Webhook Delivered" in res_webhook.formatted_reference

    # Standard public platform
    dest_devto = DestinationInfo(id="dev-1", name="DEV.to", connector_key="devto")
    res_devto = JobResult(
        destination=dest_devto,
        idempotency_key="key-3",
        job_id="job-dev",
        status="succeeded",
        live_url="https://dev.to/user/post-1",
    )
    assert res_devto.display_status == "published"
    assert "Public URL" in res_devto.formatted_reference


# ── 8. Error Handling Tests (Auth, Timeout, Polling Failure) ─────────────────

@pytest.mark.asyncio
async def test_auth_failure_rejected(sample_content_file):
    mock_get = MagicMock(return_value=MagicMock(status_code=401, is_success=False))

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get)):
        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "all",
            "--token", "invalid-token",
        ])
        assert code == 1


@pytest.mark.asyncio
async def test_polling_timeout_reported_as_failure(sample_content_file, sample_destinations_api_response):
    dest_single = {"items": [sample_destinations_api_response["items"][0]], "total": 1}

    def mock_get_handler(url, params=None):
        if "/api/v1/destinations" in url:
            return MagicMock(status_code=200, is_success=True, json=MagicMock(return_value=dest_single))
        if "/api/v1/jobs/" in url:
            # Always returns running, never finishes
            return MagicMock(
                status_code=200,
                is_success=True,
                json=MagicMock(return_value={"status": "running", "progress": 40}),
            )
        return MagicMock(status_code=404)

    mock_post = MagicMock(
        return_value=MagicMock(status_code=202, is_success=True, json=MagicMock(return_value={"job_id": "job-timeout"}))
    )

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=mock_get_handler)), \
         patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):

        code = await async_cli_entrypoint([
            "publish",
            "--input", str(sample_content_file),
            "--destinations", "all",
            "--live",
            "--token", "valid-token",
            "--timeout", "0.05",
            "--poll-interval", "0.01",
        ])

        # Timeout must result in non-zero exit code
        assert code == 1
