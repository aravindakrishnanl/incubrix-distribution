"""Lemmy connector implementation (ActivityPub protocol platform).

Authentication: JWT token obtained via username/password login.
instance_param: base_url (the Lemmy instance URL)
"""

from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.core.errors import AuthExpiredError, PlatformRateLimitError, PlatformUnavailableError
from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)
TITLE_MAX = 200
BODY_MAX = 10_000


class LemmyConnector(BaseConnector):
    key = "lemmy"
    version = "1.0.0"
    tier = "protocol"
    auth = "bot_token"

    def _base_url(self, connection: dict, destination: dict | None = None) -> str:
        return (
            connection.get("base_url")
            or (destination or {}).get("instance_param")
            or get_settings().lemmy_base_url
        )

    def _map_error(self, status_code: int) -> None:
        if status_code == 401:
            raise AuthExpiredError()
        if status_code == 429:
            raise PlatformRateLimitError()
        if status_code in (500, 502, 503, 504):
            raise PlatformUnavailableError("lemmy")

    async def _get_token(self, connection: dict[str, Any], base_url: str) -> str:
        """Obtain JWT via login. In simulation, return the stored token directly."""
        if token := connection.get("jwt_token"):
            return token
        username = connection.get("username") or get_settings().lemmy_username
        password = connection.get("password") or get_settings().lemmy_password
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/api/v3/user/login",
                json={"username_or_email": username, "password": password},
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            raise AuthExpiredError()
        return resp.json().get("jwt", "")

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        title = rendition.get("title", "")
        body = rendition.get("body", "")
        if not title:
            violations.append({"field": "title", "message": "title is required"})
        if len(title) > TITLE_MAX:
            violations.append({"field": "title", "message": f"Exceeds {TITLE_MAX} chars"})
        if len(body) > BODY_MAX:
            violations.append({"field": "body", "message": f"Exceeds {BODY_MAX} chars"})
        community_id = (
            destination.get("community_id")
            or connection.get("community_id")
            or get_settings().lemmy_community_id
        )
        if not community_id:
            violations.append({"field": "community_id", "message": "community_id required"})
        return {"ok": not violations, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_publish(rendition, destination, idempotency_key)
        base_url = self._base_url(connection, destination)
        token = await self._get_token(connection, base_url)
        community_id = (
            destination.get("community_id")
            or connection.get("community_id")
            or get_settings().lemmy_community_id
        )
        payload = {
            "name": rendition.get("title"),
            "body": rendition.get("body"),
            "community_id": int(community_id),
            "nsfw": False,
        }
        if url := rendition.get("url"):
            payload["url"] = url

        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/api/v3/post",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            from app.core.errors import AppError, ErrorCode
            raise AppError(ErrorCode.PLATFORM_CONTENT_REJECTED, f"Lemmy rejected: {resp.text[:200]}")
        data = resp.json()
        post = data.get("post_view", {}).get("post", {})
        post_id = str(post.get("id", ""))
        live_url = post.get("ap_id") or f"{base_url}/post/{post_id}"
        return {"platform_post_id": post_id, "live_url": live_url, "status": "published"}

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_status(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(f"{base_url}/api/v3/post?id={platform_post_id}")
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"status": "unknown", "live_url": None}
        post = resp.json().get("post_view", {}).get("post", {})
        return {"status": "published", "live_url": post.get("ap_id")}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_delete(platform_post_id)
        base_url = self._base_url(connection)
        token = await self._get_token(connection, base_url)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/api/v3/post/delete",
                json={"post_id": int(platform_post_id), "deleted": True},
                headers={"Authorization": f"Bearer {token}"},
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
        return {"deleted": True}

    async def fetch_metrics(self, platform_post_id, connection, since=None) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_metrics()
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(f"{base_url}/api/v3/post?id={platform_post_id}")
        if not resp.is_success:
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0, "watch_time_s": 0, "clicks": 0}
        counts = resp.json().get("post_view", {}).get("counts", {})
        return {
            "views": counts.get("read_count", 0),
            "likes": counts.get("upvotes", 0),
            "comments": counts.get("comments", 0),
            "shares": 0,
            "saves": counts.get("saved", 0) if isinstance(counts.get("saved"), int) else 0,
            "watch_time_s": 0,
            "clicks": 0,
        }

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self._base_url(connection, destination)
        token = await self._get_token(connection, base_url)
        username = connection.get("username") or get_settings().lemmy_username
        return {
            "ok": bool(token),
            "message": f"Successfully authenticated as {username}",
            "details": {"base_url": base_url, "username": username, "jwt_obtained": bool(token)},
        }
