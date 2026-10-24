"""Discourse connector implementation.

One connector, many forums. The base_url is the instance_param.
Authentication: Discourse API key + username in request headers.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.core.errors import (
    AuthExpiredError,
    DestSpecViolationError,
    PlatformRateLimitError,
    PlatformUnavailableError,
)
from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)
TITLE_MAX = 255
BODY_MAX = 32_000


class DiscourseConnector(BaseConnector):
    key = "discourse"
    version = "1.0.0"
    tier = "native"
    auth = "api_key"

    def _headers(self, connection: dict[str, Any]) -> dict[str, str]:
        settings = get_settings()
        api_key = connection.get("api_key") or settings.discourse_api_key
        api_username = connection.get("api_username") or settings.discourse_api_username or "system"
        return {
            "Api-Key": api_key,
            "Api-Username": api_username,
            "Content-Type": "application/json",
        }

    def _base_url(self, connection: dict[str, Any], destination: dict[str, Any] | None = None) -> str:
        return (
            connection.get("base_url")
            or (destination or {}).get("instance_param")
            or get_settings().discourse_base_url
        )

    def _map_error(self, status_code: int, message: str = "") -> None:
        if status_code == 401:
            raise AuthExpiredError()
        if status_code == 429:
            raise PlatformRateLimitError()
        if status_code in (500, 502, 503, 504):
            raise PlatformUnavailableError("discourse")

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        title = rendition.get("title", "")
        body = rendition.get("body", "")
        if len(title) > TITLE_MAX:
            violations.append({"field": "title", "message": f"Exceeds {TITLE_MAX} chars (got {len(title)})"})
        if not title:
            violations.append({"field": "title", "message": "title is required"})
        if len(body) > BODY_MAX:
            violations.append({"field": "body", "message": f"Exceeds {BODY_MAX} chars (got {len(body)})"})
        return {"ok": len(violations) == 0, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        if self._is_simulation():
            result = self._sim_publish(rendition, destination, idempotency_key)
            logger.info("discourse_publish_simulated", post_id=result["platform_post_id"])
            return result

        base_url = self._base_url(connection, destination)
        category_id = destination.get("category_id") or connection.get("category_id") or 1
        payload = {
            "title": rendition.get("title", "Untitled"),
            "raw": rendition.get("body", ""),
            "category": category_id,
        }

        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/posts.json",
                json=payload,
                headers=self._headers(connection),
            )

        if not resp.is_success:
            self._map_error(resp.status_code, resp.text)
            from app.core.errors import AppError, ErrorCode
            raise AppError(
                ErrorCode.PLATFORM_CONTENT_REJECTED,
                f"Discourse rejected post: {resp.text[:200]}",
            )

        data = resp.json()
        topic_id = data.get("topic_id", data.get("id"))
        post_id = str(data.get("id", ""))
        live_url = f"{base_url}/t/{topic_id}"
        logger.info("discourse_publish_ok", post_id=post_id, live_url=live_url)
        return {"platform_post_id": post_id, "live_url": live_url, "status": "published"}

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_status(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/posts/{platform_post_id}.json",
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"status": "unknown", "live_url": None}
        data = resp.json()
        topic_id = data.get("topic_id")
        live_url = f"{base_url}/t/{topic_id}" if topic_id else None
        return {"status": "published", "live_url": live_url}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_delete(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.delete(
                f"{base_url}/posts/{platform_post_id}.json",
                headers=self._headers(connection),
            )
        if resp.status_code == 404:
            return {"deleted": True}  # already gone
        if not resp.is_success:
            self._map_error(resp.status_code)
        logger.info("discourse_delete_ok", post_id=platform_post_id)
        return {"deleted": True}

    async def fetch_metrics(self, platform_post_id, connection, since=None) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_metrics()
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/posts/{platform_post_id}.json",
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0, "watch_time_s": 0, "clicks": 0}
        data = resp.json()
        return {
            "views": data.get("reads", 0),
            "likes": data.get("like_count", 0),
            "comments": data.get("reply_count", 0),
            "shares": 0,
            "saves": 0,
            "watch_time_s": 0,
            "clicks": 0,
        }

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self._base_url(connection, destination)
        headers = self._headers(connection)
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.get(f"{base_url}/session/current.json", headers=headers)
        if not resp.is_success:
            self._map_error(resp.status_code, resp.text)
            return {"ok": False, "status_code": resp.status_code, "message": f"Auth check failed: {resp.text[:200]}"}
        data = resp.json()
        username = data.get("current_user", {}).get("username")
        return {"ok": True, "message": f"Authenticated as {username}", "details": {"username": username, "base_url": base_url}}
