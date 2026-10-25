"""Tests verifying live HTTP execution, error handling, and connectivity checks.

Verifies:
1. Live mode makes actual HTTP requests (mocked at httpx transport layer).
2. Live mode does not return fabricated responses.
3. Authentication failures (401) raise AuthExpiredError.
4. Rate limits (429) raise PlatformRateLimitError.
5. Server errors (500/503) raise PlatformUnavailableError.
6. check_connectivity works safely without creating content.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.connectors.registry import get_connector, init_registry
from app.core.errors import (
    AppError,
    AuthExpiredError,
    ErrorCode,
    PlatformRateLimitError,
    PlatformUnavailableError,
)

init_registry()


@pytest.fixture
def disable_simulation():
    """Ensure simulation mode is turned off for live connector tests."""
    with patch("app.connectors.base.BaseConnector._is_simulation", return_value=False):
        yield


@pytest.mark.asyncio
async def test_discourse_live_publish_makes_http_post(disable_simulation):
    connector = get_connector("discourse")
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_resp.json.return_value = {"id": 999, "topic_id": 888}

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        res = await connector.publish(
            rendition={"title": "Real Topic", "body": "Real body"},
            destination={"category_id": 2},
            connection={"base_url": "https://forum.example.com", "api_key": "k", "api_username": "u"},
            idempotency_key="idem-live-1",
        )

        assert res["platform_post_id"] == "999"
        assert "888" in res["live_url"]
        assert res.get("_simulated") is not True
        mock_client.post.assert_called_once()
        call_url = mock_client.post.call_args[0][0]
        assert call_url == "https://forum.example.com/posts.json"


@pytest.mark.asyncio
async def test_discourse_live_401_raises_auth_error(disable_simulation):
    connector = get_connector("discourse")
    mock_resp = MagicMock(status_code=401, is_success=False, text="Invalid API key")

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(AuthExpiredError):
            await connector.publish(
                rendition={"title": "Real Topic", "body": "Real body"},
                destination={},
                connection={"base_url": "https://forum.example.com", "api_key": "bad"},
                idempotency_key="idem-live-2",
            )


@pytest.mark.asyncio
async def test_devto_live_publish_and_rate_limit(disable_simulation):
    connector = get_connector("devto")
    mock_resp_429 = MagicMock(status_code=429, is_success=False, text="Rate limit exceeded")

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp_429)

        with pytest.raises(PlatformRateLimitError):
            await connector.publish(
                rendition={"title": "Dev Post", "body": "Dev content"},
                destination={},
                connection={"base_url": "https://dev.to/api", "api_key": "dev-key"},
                idempotency_key="idem-live-3",
            )


@pytest.mark.asyncio
async def test_ghost_live_503_raises_unavailable(disable_simulation):
    connector = get_connector("ghost")
    mock_resp_503 = MagicMock(status_code=503, is_success=False, text="Ghost service down")

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp_503)

        with pytest.raises(PlatformUnavailableError):
            await connector.publish(
                rendition={"title": "Ghost Post", "body": "Ghost content"},
                destination={},
                connection={"base_url": "https://ghost.example.com", "admin_api_key": "abc:123"},
                idempotency_key="idem-live-4",
            )


@pytest.mark.asyncio
async def test_lemmy_check_connectivity(disable_simulation):
    connector = get_connector("lemmy")
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_resp.json.return_value = {"jwt": "fake.jwt.token"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        res = await connector.check_connectivity(
            connection={"base_url": "https://lemmy.example.com", "username": "u", "password": "p"}
        )
        assert res["ok"] is True
        assert res["details"]["jwt_obtained"] is True


@pytest.mark.asyncio
async def test_assisted_check_connectivity():
    connector = get_connector("assisted")
    res = await connector.check_connectivity({})
    assert res["ok"] is True
    assert res["details"]["requires_auth"] is False


@pytest.mark.asyncio
async def test_webhook_hmac_check_connectivity():
    connector = get_connector("webhook_hmac")
    res = await connector.check_connectivity(
        connection={"webhook_url": "https://example.com/webhook", "hmac_secret": "sec"}
    )
    assert res["ok"] is True
    assert res["details"]["has_secret"] is True


@pytest.mark.asyncio
async def test_check_connectivity_api_route(async_client):
    for key in ["discourse", "lemmy", "devto", "ghost", "webhook_hmac", "assisted"]:
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "current_user": {"username": "admin"},
            "jwt": "fake.jwt",
            "site": {"title": "Ghost Site", "version": "5.0"},
        }
        with patch("httpx.AsyncClient") as mock_cls:
            mock_inst = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_inst.get = AsyncMock(return_value=mock_resp)
            mock_inst.post = AsyncMock(return_value=mock_resp)

            resp = await async_client.post(
                f"/connector/v1/{key}/check_connectivity",
                json={
                    "connection": {
                        "base_url": "https://example.com",
                        "api_key": "k",
                        "admin_api_key": "id:0123456789abcdef",
                        "webhook_url": "https://example.com/hook",
                    }
                },
            )
            assert resp.status_code == 200, f"Failed for {key}: {resp.text}"
            data = resp.json()
            assert data["ok"] is True


def test_settings_env_aliases():
    from app.core.settings import Settings
    s = Settings(_env_file=None, dev_api_key="my-key", dev_api_base_url="https://mydev.to/api", ghost_api_key="gkey:123")
    assert s.devto_api_key == "my-key"
    assert s.devto_api_base_url == "https://mydev.to/api"
    assert s.ghost_admin_api_key == "gkey:123"


# ── DEV.to and Ghost Draft Regression Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_devto_live_payload_published_false_preserved(disable_simulation):
    connector = get_connector("devto")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {"id": 12345, "url": "https://dev.to/user/draft-article", "published": False}

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await connector.publish(
            rendition={"title": "Draft Article", "body": "Draft body", "published": False},
            destination={},
            connection={"base_url": "https://dev.to/api", "api_key": "test-key"},
            idempotency_key="devto-draft-1",
        )

        # Verify outgoing payload
        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["article"]["published"] is False
        assert sent_payload["article"]["title"] == "Draft Article"
        assert result["status"] == "draft"
        assert result["platform_post_id"] == "12345"


@pytest.mark.asyncio
async def test_devto_live_payload_default_published_true(disable_simulation):
    connector = get_connector("devto")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {"id": 12346, "url": "https://dev.to/user/public-article", "published": True}

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await connector.publish(
            rendition={"title": "Public Article", "body": "Public body"},
            destination={},
            connection={"base_url": "https://dev.to/api", "api_key": "test-key"},
            idempotency_key="devto-pub-1",
        )

        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["article"]["published"] is True
        assert result["status"] == "published"


@pytest.mark.asyncio
async def test_devto_live_payload_rendition_precedence(disable_simulation):
    connector = get_connector("devto")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {"id": 12347, "url": "https://dev.to/user/article", "published": False}

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        # Destination says published=True, but rendition explicitly says published=False
        await connector.publish(
            rendition={"title": "Article", "body": "Body", "published": False},
            destination={"published": True},
            connection={"base_url": "https://dev.to/api", "api_key": "test-key"},
            idempotency_key="devto-prec-1",
        )

        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["article"]["published"] is False


@pytest.mark.asyncio
async def test_ghost_live_payload_draft_status_preserved(disable_simulation):
    connector = get_connector("ghost")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {
        "posts": [{"id": "ghost-draft-id", "url": "https://ghost.example.com/draft", "status": "draft"}]
    }

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await connector.publish(
            rendition={"title": "Ghost Draft Post", "body": "Draft content", "status": "draft"},
            destination={},
            connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            idempotency_key="ghost-draft-1",
        )

        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["posts"][0]["status"] == "draft"
        assert sent_payload["posts"][0]["title"] == "Ghost Draft Post"
        assert result["status"] == "draft"
        assert result["platform_post_id"] == "ghost-draft-id"


@pytest.mark.asyncio
async def test_ghost_live_payload_default_published_status(disable_simulation):
    connector = get_connector("ghost")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {
        "posts": [{"id": "ghost-pub-id", "url": "https://ghost.example.com/live", "status": "published"}]
    }

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await connector.publish(
            rendition={"title": "Ghost Public Post", "body": "Live content"},
            destination={},
            connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            idempotency_key="ghost-pub-1",
        )

        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["posts"][0]["status"] == "published"
        assert result["status"] == "published"


@pytest.mark.asyncio
async def test_devto_live_get_status_reports_draft(disable_simulation):
    connector = get_connector("devto")
    response = MagicMock(
        status_code=200,
        is_success=True,
    )
    response.json.return_value = {
        "id": 123,
        "published": False,
        "url": "https://dev.to/test/draft",
    }

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        client_cls.return_value.__aexit__ = AsyncMock(
            return_value=None
        )
        client.get = AsyncMock(return_value=response)

        result = await connector.get_status(
            "123",
            {"base_url": "https://dev.to/api", "api_key": "test"},
        )

    assert result["status"] == "draft"
    assert result["live_url"] == "https://dev.to/test/draft"


@pytest.mark.asyncio
async def test_devto_live_delete_unpublishes_article(disable_simulation):
    connector = get_connector("devto")
    response = MagicMock(status_code=200, is_success=True)

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        client_cls.return_value.__aexit__ = AsyncMock(
            return_value=None
        )
        client.put = AsyncMock(return_value=response)

        result = await connector.delete(
            "123",
            {"base_url": "https://dev.to/api", "api_key": "test"},
        )

    assert result["deleted"] is True
    sent = client.put.call_args.kwargs["json"]
    assert sent == {"article": {"published": False}}


@pytest.mark.asyncio
async def test_ghost_live_get_status_reports_draft(disable_simulation):
    connector = get_connector("ghost")
    response = MagicMock(status_code=200, is_success=True)
    response.json.return_value = {
        "posts": [{
            "id": "ghost-draft-123",
            "status": "draft",
            "url": "https://ghost.example.com/draft/",
        }]
    }

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        client_cls.return_value.__aexit__ = AsyncMock(
            return_value=None
        )
        client.get = AsyncMock(return_value=response)

        result = await connector.get_status(
            "ghost-draft-123",
            {
                "base_url": "https://ghost.example.com",
                "admin_api_key": "kid:0123456789abcdef",
            },
        )

    assert result["status"] == "draft"
    assert result["live_url"] == "https://ghost.example.com/draft/"


@pytest.mark.asyncio
async def test_ghost_live_delete_success(disable_simulation):
    connector = get_connector("ghost")
    response = MagicMock(status_code=204, is_success=True)

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        client_cls.return_value.__aexit__ = AsyncMock(
            return_value=None
        )
        client.delete = AsyncMock(return_value=response)

        result = await connector.delete(
            "ghost-post-123",
            {
                "base_url": "https://ghost.example.com",
                "admin_api_key": "kid:0123456789abcdef",
            },
        )

    assert result["deleted"] is True
    client.delete.assert_called_once()
    assert "ghost-post-123" in client.delete.call_args.args[0]


@pytest.mark.asyncio
async def test_ghost_live_delete_already_missing(disable_simulation):
    connector = get_connector("ghost")
    response = MagicMock(status_code=404, is_success=False)

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        client_cls.return_value.__aexit__ = AsyncMock(
            return_value=None
        )
        client.delete = AsyncMock(return_value=response)

        result = await connector.delete(
            "missing-post",
            {
                "base_url": "https://ghost.example.com",
                "admin_api_key": "kid:0123456789abcdef",
            },
        )

    assert result["deleted"] is True

@pytest.mark.asyncio
async def test_ghost_live_payload_rendition_precedence(disable_simulation):
    connector = get_connector("ghost")
    mock_resp = MagicMock(status_code=201, is_success=True)
    mock_resp.json.return_value = {
        "posts": [{"id": "ghost-id", "url": "https://ghost.example.com/post", "status": "draft"}]
    }

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        # Destination says status=published, but rendition explicitly says status=draft
        await connector.publish(
            rendition={"title": "Post", "body": "Body", "status": "draft"},
            destination={"status": "published"},
            connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            idempotency_key="ghost-prec-1",
        )

        sent_payload = mock_client.post.call_args[1]["json"]
        assert sent_payload["posts"][0]["status"] == "draft"


# ── Ghost publish_draft verification tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_ghost_publish_draft_success(disable_simulation):
    connector = get_connector("ghost")
    post_id = "draft_post_123"
    expected_title = "[TEST DRAFT] IncuBrix Ghost Integration Verification"
    updated_at = "2026-10-25T08:00:00.000Z"

    mock_get_resp = MagicMock(status_code=200, is_success=True)
    mock_get_resp.json.return_value = {
        "posts": [{
            "id": post_id,
            "title": expected_title,
            "status": "draft",
            "updated_at": updated_at,
            "url": "https://ghost.example.com/p/draft_post_123/",
        }]
    }

    mock_put_resp = MagicMock(status_code=200, is_success=True)
    mock_put_resp.json.return_value = {
        "posts": [{
            "id": post_id,
            "title": expected_title,
            "status": "published",
            "updated_at": "2026-10-25T08:05:00.000Z",
            "url": "https://ghost.example.com/incubrix-verification/",
        }]
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.put = AsyncMock(return_value=mock_put_resp)
        mock_client.post = AsyncMock()

        result = await connector.publish_draft(
            platform_post_id=post_id,
            connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
        )

        # 1. Assert GET was called with the post ID URL
        mock_client.get.assert_called_once()
        assert f"/ghost/api/admin/posts/{post_id}/" in mock_client.get.call_args[0][0]

        # 2. Assert PUT was called with status="published" and the retrieved updated_at
        mock_client.put.assert_called_once()
        put_url = mock_client.put.call_args[0][0]
        assert f"/ghost/api/admin/posts/{post_id}/" in put_url
        put_body = mock_client.put.call_args[1]["json"]
        assert put_body == {
            "posts": [{
                "status": "published",
                "updated_at": updated_at,
            }]
        }

        # 3. Assert POST was NEVER called (never creates new post)
        mock_client.post.assert_not_called()

        # 4. Assert returned result contains status and public URL
        assert result["platform_post_id"] == post_id
        assert result["status"] == "published"
        assert result["live_url"] == "https://ghost.example.com/incubrix-verification/"
        assert result["title"] == expected_title


@pytest.mark.asyncio
async def test_ghost_publish_draft_wrong_title_rejected(disable_simulation):
    connector = get_connector("ghost")
    post_id = "prod_post_999"

    mock_get_resp = MagicMock(status_code=200, is_success=True)
    mock_get_resp.json.return_value = {
        "posts": [{
            "id": post_id,
            "title": "Important Live Production Article",
            "status": "draft",
            "updated_at": "2026-10-25T08:00:00.000Z",
        }]
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.put = AsyncMock()
        mock_client.post = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await connector.publish_draft(
                platform_post_id=post_id,
                connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            )

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "Refusing to publish" in exc_info.value.message

        # Assert no modification took place
        mock_client.put.assert_not_called()
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_ghost_publish_draft_get_failure(disable_simulation):
    connector = get_connector("ghost")
    post_id = "missing_post"

    mock_get_resp = MagicMock(status_code=404, is_success=False, text="Post not found")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.put = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await connector.publish_draft(
                platform_post_id=post_id,
                connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            )

        assert exc_info.value.code == ErrorCode.PLATFORM_CONTENT_REJECTED
        assert "HTTP 404" in exc_info.value.message
        mock_client.put.assert_not_called()


@pytest.mark.asyncio
async def test_ghost_publish_draft_put_failure(disable_simulation):
    connector = get_connector("ghost")
    post_id = "draft_post_123"

    mock_get_resp = MagicMock(status_code=200, is_success=True)
    mock_get_resp.json.return_value = {
        "posts": [{
            "id": post_id,
            "title": "[TEST DRAFT] IncuBrix Ghost Integration Verification",
            "status": "draft",
            "updated_at": "2026-10-25T08:00:00.000Z",
        }]
    }

    mock_put_resp = MagicMock(
        status_code=422,
        is_success=False,
        text="Validation error: Collision detected (stale updated_at)",
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.put = AsyncMock(return_value=mock_put_resp)

        with pytest.raises(AppError) as exc_info:
            await connector.publish_draft(
                platform_post_id=post_id,
                connection={"base_url": "https://ghost.example.com", "admin_api_key": "kid:0123456789abcdef"},
            )

        assert exc_info.value.code == ErrorCode.PLATFORM_CONTENT_REJECTED
        assert "HTTP 422" in exc_info.value.message


@pytest.mark.asyncio
async def test_ghost_publish_draft_simulation_mode():
    connector = get_connector("ghost")
    post_id = "draft_sim_456"

    # Default simulation mode (not forced live)
    result = await connector.publish_draft(platform_post_id=post_id)
    assert result["_simulated"] is True
    assert result["platform_post_id"] == post_id
    assert result["status"] == "published"
    assert "https://sim.example.com" in result["live_url"]
