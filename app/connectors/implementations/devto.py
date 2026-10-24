"""Dev.to connector implementation.

Authentication: API key in the api-key header.
No instance_param — Dev.to is a single global platform.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.core.errors import AuthExpiredError, PlatformRateLimitError, PlatformUnavailableError
from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)
TITLE_MAX = 128


class DevToConnector(BaseConnector):
    key = "devto"
    version = "1.0.0"
    tier = "native"
    auth = "api_key"

    def _api_key(self, connection: dict) -> str:
        return connection.get("api_key") or get_settings().devto_api_key

    def _base_url(self, connection: dict) -> str:
        return connection.get("base_url") or get_settings().devto_api_base_url

    def _headers(self, connection: dict) -> dict[str, str]:
        return {"api-key": self._api_key(connection), "Content-Type": "application/json"}

    def _map_error(self, status_code: int) -> None:
        if status_code == 401:
            raise AuthExpiredError()
        if status_code == 429:
            raise PlatformRateLimitError()
        if status_code in (500, 502, 503, 504):
            raise PlatformUnavailableError("devto")

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        title = rendition.get("title", "")
        if not title:
            violations.append({"field": "title", "message": "title is required"})
        if len(title) > TITLE_MAX:
            violations.append({"field": "title", "message": f"Exceeds {TITLE_MAX} chars"})
        return {"ok": not violations, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_publish(rendition, destination, idempotency_key)
        base_url = self._base_url(connection)
        tags = rendition.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        tags = tags[:4]  # Dev.to allows max 4 tags
        # Determine published status: check rendition first, then destination, default to True
        published = True
        if "published" in rendition:
            published = bool(rendition["published"])
        elif "published" in (destination or {}):
            published = bool(destination["published"])
        elif "draft" in rendition:
            published = not bool(rendition["draft"])
        elif "draft" in (destination or {}):
            published = not bool(destination["draft"])

        payload = {
            "article": {
                "title": rendition.get("title"),
                "body_markdown": rendition.get("body", ""),
                "published": published,
                "tags": tags,
            }
        }
        if canonical := rendition.get("canonical_url"):
            payload["article"]["canonical_url"] = canonical

        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/articles",
                json=payload,
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            from app.core.errors import AppError, ErrorCode
            raise AppError(ErrorCode.PLATFORM_CONTENT_REJECTED, f"Dev.to rejected: {resp.text[:200]}")
        data = resp.json()
        post_id = str(data.get("id", ""))
        live_url = data.get("url", "")
        status = "published" if data.get("published", published) else "draft"
        return {"platform_post_id": post_id, "live_url": live_url, "status": status}

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_status(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/articles/{platform_post_id}",
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"status": "unknown", "live_url": None}
        data = resp.json()
        return {"status": "published" if data.get("published") else "draft", "live_url": data.get("url")}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_delete(platform_post_id)
        # Dev.to does not support DELETE via API; unpublish as best-effort
        base_url = self._base_url(connection)
        payload = {"article": {"published": False}}
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.put(
                f"{base_url}/articles/{platform_post_id}",
                json=payload,
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
        return {"deleted": True}

    async def fetch_metrics(self, platform_post_id, connection, since=None) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_metrics()
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/articles/{platform_post_id}",
                headers=self._headers(connection),
            )
        if not resp.is_success:
            return {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0, "watch_time_s": 0, "clicks": 0}
        data = resp.json()
        return {
            "views": data.get("page_views_count", 0),
            "likes": data.get("positive_reactions_count", 0),
            "comments": data.get("comments_count", 0),
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
        base_url = self._base_url(connection)
        headers = self._headers(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(f"{base_url}/articles/me", headers=headers)
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"ok": False, "status_code": resp.status_code, "message": f"Auth check failed: {resp.text[:200]}"}
        articles = resp.json()
        return {
            "ok": True,
            "message": f"Successfully authenticated with DEV.to ({len(articles)} existing articles)",
            "details": {"base_url": base_url, "article_count": len(articles)},
        }
