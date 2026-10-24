"""Abstract connector interface.

Every connector must implement this interface. Methods return data only;
they never write to the IncuBrix database (the runtime layer owns persistence).

Method signatures match Appendix A exactly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Base class for all IncuBrix distribution connectors."""

    key: str           # unique connector identifier, e.g. "discourse"
    version: str       # semver string
    tier: str          # native | protocol | bridge | feed | assisted
    auth: str          # oauth2 | api_key | bot_token | none

    # ── Simulation mode helpers ────────────────────────────────────────────────

    @staticmethod
    def _is_simulation() -> bool:
        """Return True if SIMULATION_MODE is enabled."""
        from app.core.settings import get_settings
        return get_settings().simulation_mode

    def _sim_publish(self, rendition: dict, destination: dict, idempotency_key: str) -> dict[str, Any]:
        """Return a simulated publish result — no real HTTP calls made."""
        import time
        fake_id = f"sim-{self.key}-{idempotency_key[:8]}"
        fake_url = (destination or {}).get("url") or f"https://sim.example.com/{fake_id}"
        return {
            "platform_post_id": fake_id,
            "live_url": fake_url,
            "status": "published",
            "_simulated": True,
        }

    def _sim_status(self, platform_post_id: str) -> dict[str, Any]:
        return {"status": "published", "live_url": None, "_simulated": True}

    def _sim_delete(self, platform_post_id: str) -> dict[str, Any]:
        return {"deleted": True, "_simulated": True}

    def _sim_metrics(self) -> dict[str, Any]:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0,
                "saves": 0, "watch_time_s": 0, "clicks": 0, "_simulated": True}

    # ── Required methods ─────────────────────────────────────────────────────

    @abstractmethod
    async def validate(
        self,
        rendition: dict[str, Any],
        destination: dict[str, Any],
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate rendition against destination spec.

        Returns: {ok: bool, violations: list[{field, message}]}
        """

    @abstractmethod
    async def publish(
        self,
        rendition: dict[str, Any],
        destination: dict[str, Any],
        connection: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Publish rendition to destination.

        Returns: {platform_post_id, live_url, status}
        """

    @abstractmethod
    async def get_status(
        self,
        platform_post_id: str,
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        """Get current status of a published post.

        Returns: {status, live_url}
        """

    @abstractmethod
    async def delete(
        self,
        platform_post_id: str,
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        """Delete a published post.

        Returns: {deleted: bool}
        """

    # ── Optional methods ──────────────────────────────────────────────────────

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: dict[str, Any],
        since: str | None = None,
    ) -> dict[str, Any]:
        """Fetch engagement metrics for a published post.

        Returns: {views, likes, comments, shares, saves, watch_time_s, clicks}
        """
        raise NotImplementedError(f"Connector {self.key!r} does not support fetch_metrics")

    async def refresh_auth(
        self,
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        """Refresh expiring authentication credentials.

        Returns: {expires_at}
        """
        raise NotImplementedError(f"Connector {self.key!r} does not support refresh_auth")

    async def build_assist_pack(
        self,
        rendition: dict[str, Any],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an assisted publishing pack for human posting.

        Returns: {files[], caption, deep_link, checklist[]}
        Assisted tier only.
        """
        raise NotImplementedError(f"Connector {self.key!r} does not support build_assist_pack")

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check authentication and connectivity without publishing any content.

        Returns: {ok: bool, message: str, details: dict}
        """
        raise NotImplementedError(f"Connector {self.key!r} does not support check_connectivity")
