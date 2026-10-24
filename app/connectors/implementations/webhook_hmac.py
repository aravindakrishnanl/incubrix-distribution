"""Generic HMAC-SHA256 signed webhook connector.

Sends a signed JSON payload to any partner HTTP endpoint.
Authentication: HMAC-SHA256 signature in X-IncuBrix-Signature header.
instance_param: webhook_url
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.core.errors import PlatformRateLimitError, PlatformUnavailableError
from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)


class WebhookHmacConnector(BaseConnector):
    key = "webhook_hmac"
    version = "1.0.0"
    tier = "bridge"
    auth = "api_key"

    def _webhook_url(self, connection: dict, destination: dict | None = None) -> str:
        return (
            connection.get("webhook_url")
            or connection.get("url")
            or (destination or {}).get("instance_param")
            or (destination or {}).get("target_url")
            or (destination or {}).get("url")
            or ""
        )

    def _sign(self, payload_bytes: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(
            secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()

    def _map_error(self, status_code: int) -> None:
        if status_code == 429:
            raise PlatformRateLimitError()
        if status_code in (500, 502, 503, 504):
            raise PlatformUnavailableError("webhook_hmac")

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        url = self._webhook_url(connection, destination)
        if not url:
            violations.append({"field": "webhook_url", "message": "webhook_url is required in connection or destination"})
        body = json.dumps(rendition).encode()
        if len(body) > 65536:
            violations.append({"field": "rendition", "message": "Payload exceeds 65536 bytes"})
        return {"ok": not violations, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        if self._is_simulation():
            url = self._webhook_url(connection, destination) or "https://sim.example.com/webhook"
            fake_id = f"sim-webhook-{idempotency_key[:8]}"
            logger.info("webhook_publish_simulated", fake_id=fake_id)
            return {"platform_post_id": fake_id, "live_url": url, "status": "delivered", "_simulated": True}
        url = self._webhook_url(connection, destination)
        secret = connection.get("hmac_secret") or get_settings().hmac_signing_secret
        if not secret:
            from app.core.errors import AppError, ErrorCode
            raise AppError(ErrorCode.DEST_SPEC_VIOLATION, "HMAC signing secret is required for webhook signing")
        payload = {
            "idempotency_key": idempotency_key,
            "rendition": rendition,
            "destination": {k: v for k, v in (destination or {}).items() if k not in ("credentials",)},
        }
        body_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = self._sign(body_bytes, secret)

        async with httpx.AsyncClient(timeout=get_settings().http_timeout_seconds) as client:
            resp = await client.post(
                url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-IncuBrix-Signature": signature,
                    "X-Idempotency-Key": idempotency_key,
                },
            )
        if not resp.is_success:
            self._map_error(resp.status_code)
            from app.core.errors import AppError, ErrorCode
            raise AppError(ErrorCode.PLATFORM_UNAVAILABLE, f"Webhook returned {resp.status_code}")
        try:
            data = resp.json()
        except Exception:
            data = {}
        post_id = str(data.get("id") or idempotency_key)
        return {"platform_post_id": post_id, "live_url": url, "status": "delivered"}

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        # Webhooks are fire-and-forget; status is always "delivered" if sent
        return {"status": "delivered", "live_url": connection.get("webhook_url", "")}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        if self._is_simulation():
            return {"deleted": True}
        # Send a DELETE-event webhook
        url = self._webhook_url(connection)
        if not url:
            return {"deleted": True}

        secret = connection.get("hmac_secret") or get_settings().hmac_signing_secret
        payload = {"event": "delete", "platform_post_id": platform_post_id}
        body_bytes = json.dumps(payload).encode()
        signature = self._sign(body_bytes, secret)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    url,
                    content=body_bytes,
                    headers={"Content-Type": "application/json", "X-IncuBrix-Signature": signature},
                )
        except Exception:
            pass
        return {"deleted": True}

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._webhook_url(connection, destination)
        secret = connection.get("hmac_secret") or get_settings().hmac_signing_secret
        if not url:
            return {"ok": False, "message": "No webhook_url configured in connection or destination"}
        return {
            "ok": True,
            "message": "Webhook connector configured with endpoint and HMAC secret",
            "details": {"webhook_url": url, "has_secret": bool(secret)},
        }
