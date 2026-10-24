"""Ghost connector implementation.

Authentication: Ghost Admin API key (JWT-signed).
instance_param: base_url
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.core.errors import AuthExpiredError, PlatformRateLimitError, PlatformUnavailableError
from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)


def _make_ghost_jwt(admin_api_key: str) -> str:
    """Create a short-lived JWT for Ghost Admin API authentication."""
    import base64
    import hmac as hmac_lib
    import json as json_lib

    try:
        key_id, secret_hex = admin_api_key.split(":")
        secret_bytes = bytes.fromhex(secret_hex)
    except ValueError:
        return admin_api_key  # pass-through for test tokens

    header = base64.urlsafe_b64encode(
        json_lib.dumps({"alg": "HS256", "typ": "JWT", "kid": key_id}).encode()
    ).rstrip(b"=")
    iat = int(time.time())
    payload = base64.urlsafe_b64encode(
        json_lib.dumps({"iat": iat, "exp": iat + 300, "aud": "/admin/"}).encode()
    ).rstrip(b"=")
    signing_input = header + b"." + payload
    sig = base64.urlsafe_b64encode(
        hmac_lib.new(secret_bytes, signing_input, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (signing_input + b"." + sig).decode()


class GhostConnector(BaseConnector):
    key = "ghost"
    version = "1.0.0"
    tier = "native"
    auth = "api_key"

    def _base_url(self, connection: dict, destination: dict | None = None) -> str:
        return (
            connection.get("base_url")
            or (destination or {}).get("instance_param")
            or get_settings().ghost_api_base_url
        )

    def _admin_key(self, connection: dict) -> str:
        return connection.get("admin_api_key") or connection.get("api_key") or get_settings().ghost_admin_api_key

    def _headers(self, connection: dict) -> dict[str, str]:
        jwt = _make_ghost_jwt(self._admin_key(connection))
        return {
            "Authorization": f"Ghost {jwt}",
            "Content-Type": "application/json",
            "Accept-Version": "v5.0",
        }

    def _map_error(self, status_code: int) -> None:
        if status_code == 401:
            raise AuthExpiredError()
        if status_code == 429:
            raise PlatformRateLimitError()
        if status_code in (500, 502, 503, 504):
            raise PlatformUnavailableError("ghost")

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        if not rendition.get("title"):
            violations.append({"field": "title", "message": "title is required"})
        return {"ok": not violations, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_publish(rendition, destination, idempotency_key)
        base_url = self._base_url(connection, destination)
        # Determine post status: check rendition first, then destination, default to 'published'
        status = "published"
        if "status" in rendition:
            status = str(rendition["status"]).lower()
        elif "status" in (destination or {}):
            status = str(destination["status"]).lower()
        elif rendition.get("published") is False or (destination or {}).get("published") is False:
            status = "draft"
        elif rendition.get("draft") is True or (destination or {}).get("draft") is True:
            status = "draft"

        payload = {
            "posts": [{
                "title": rendition.get("title", "Untitled"),
                "html": rendition.get("html") or f"<p>{rendition.get('body', '')}</p>",
                "status": status,
            }]
        }
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/ghost/api/admin/posts/",
                json=payload,
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            from app.core.errors import AppError, ErrorCode
            raise AppError(ErrorCode.PLATFORM_CONTENT_REJECTED, f"Ghost rejected: {resp.text[:200]}")
        posts = resp.json().get("posts", [{}])
        post = posts[0] if posts else {}
        post_id = str(post.get("id", ""))
        live_url = post.get("url", "")
        post_status = post.get("status") or status
        return {"platform_post_id": post_id, "live_url": live_url, "status": post_status}

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_status(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(
                f"{base_url}/ghost/api/admin/posts/{platform_post_id}/",
                headers=self._headers(connection),
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"status": "unknown", "live_url": None}
        posts = resp.json().get("posts", [{}])
        post = posts[0] if posts else {}
        return {"status": post.get("status", "unknown"), "live_url": post.get("url")}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return self._sim_delete(platform_post_id)
        base_url = self._base_url(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.delete(
                f"{base_url}/ghost/api/admin/posts/{platform_post_id}/",
                headers=self._headers(connection),
            )
        if resp.status_code == 404:
            return {"deleted": True}
        if not resp.is_success:
            self._map_error(resp.status_code)
        return {"deleted": True}

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self._base_url(connection, destination)
        headers = self._headers(connection)
        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.get(f"{base_url}/ghost/api/admin/site/", headers=headers)
        if not resp.is_success:
            self._map_error(resp.status_code)
            return {"ok": False, "status_code": resp.status_code, "message": f"Auth check failed: {resp.text[:200]}"}
        site = resp.json().get("site", {})
        return {
            "ok": True,
            "message": f"Successfully authenticated with Ghost site '{site.get('title')}'",
            "details": {"base_url": base_url, "title": site.get("title"), "version": site.get("version")},
        }
