"""Discourse connector unit tests with mocked HTTP."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.connectors.implementations.discourse import DiscourseConnector


@pytest.fixture
def connector():
    return DiscourseConnector()


@pytest.mark.asyncio
async def test_validate_title_too_long(connector):
    result = await connector.validate(
        rendition={"title": "x" * 300, "body": "body"},
        destination={},
        connection={"base_url": "http://mock.example.com", "api_key": "key"},
    )
    assert result["ok"] is False
    assert any(v["field"] == "title" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_missing_title(connector):
    result = await connector.validate(
        rendition={"title": "", "body": "body"},
        destination={},
        connection={},
    )
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_validate_valid_content(connector):
    result = await connector.validate(
        rendition={"title": "Valid Title", "body": "Valid body"},
        destination={},
        connection={},
    )
    assert result["ok"] is True
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_publish_success(connector):
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"id": "123", "topic_id": "456"}

    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(connector, "_is_simulation", return_value=False):
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await connector.publish(
            rendition={"title": "Test Post", "body": "Hello"},
            destination={"category_id": 1},
            connection={"base_url": "http://mock.example.com", "api_key": "key"},
            idempotency_key="test-key-001",
        )

    assert result["platform_post_id"] == "123"
    assert "456" in result["live_url"]
    assert result["status"] == "published"



@pytest.mark.asyncio
async def test_delete_success(connector):
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.delete = AsyncMock(return_value=mock_response)

        result = await connector.delete(
            platform_post_id="123",
            connection={"base_url": "http://mock.example.com", "api_key": "key"},
        )
    assert result["deleted"] is True


@pytest.mark.asyncio
async def test_delete_already_gone(connector):
    """404 on delete should return deleted=True (already gone)."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.delete = AsyncMock(return_value=mock_response)

        result = await connector.delete("123", {"base_url": "http://mock.example.com", "api_key": "k"})
    assert result["deleted"] is True
