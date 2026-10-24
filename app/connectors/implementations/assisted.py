"""Assisted Publishing connector.

Builds a ready-to-post pack for human posting where automation is not allowed.
Returns: {files[], caption, deep_link, checklist[]}
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.core.logging import get_logger

logger = get_logger(__name__)


class AssistedConnector(BaseConnector):
    key = "assisted"
    version = "1.0.0"
    tier = "assisted"
    auth = "none"

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        if not rendition.get("title"):
            violations.append({"field": "title", "message": "title is required for assisted pack"})
        return {"ok": not violations, "violations": violations}

    async def publish(self, rendition, destination, connection, idempotency_key) -> dict[str, Any]:
        # Assisted publishing does not automate posting; publish returns a pack reference
        pack = await self.build_assist_pack(rendition, destination)
        return {
            "platform_post_id": f"assisted:{idempotency_key}",
            "live_url": pack.get("deep_link", ""),
            "status": "assist_ready",
        }

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        return {"status": "assist_ready", "live_url": None}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        return {"deleted": True}

    async def build_assist_pack(self, rendition, destination) -> dict[str, Any]:
        """Build the assisted publishing pack.

        Returns:
          files: list of file dicts {name, content_type, url_or_content}
          caption: suggested caption/body text
          deep_link: direct link to post in the destination (if available)
          checklist: list of rule/policy checks for the human poster
        """
        title = rendition.get("title", "")
        body = rendition.get("body", "")
        rules_url = destination.get("rules_url", "")
        dest_url = destination.get("url", "")
        platform = destination.get("platform_key", "unknown")

        # Build checklist from destination rules
        checklist = [
            {"check": "Read community rules before posting", "url": rules_url or dest_url, "required": True},
            {"check": "Ensure title follows platform guidelines", "required": True},
            {"check": "Remove or disclose AI-generated content if required", "required": destination.get("disclosure_required", False)},
            {"check": "Confirm self-promotion is allowed", "required": not destination.get("self_promo_allowed", True)},
            {"check": "Confirm frequency cap has not been exceeded", "required": bool(destination.get("frequency_cap"))},
            {"check": "Delete post within 10 minutes if it is a test", "required": True},
        ]

        # Build file list (text file with ready-to-paste content)
        post_text = f"# {title}\n\n{body}"
        files = [
            {
                "name": "post.md",
                "content_type": "text/markdown",
                "content": post_text,
            }
        ]
        if images := rendition.get("images", []):
            for i, img in enumerate(images):
                files.append({"name": f"image_{i+1}", "content_type": "image/*", "url": img})

        deep_link = dest_url  # direct link to the destination; human pastes and posts

        logger.info("assisted_pack_built", platform=platform, file_count=len(files))
        return {
            "files": files,
            "caption": body[:300] + ("..." if len(body) > 300 else ""),
            "deep_link": deep_link,
            "checklist": [c for c in checklist if c.get("required") or True],
        }

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Assisted publishing ready (human-in-the-loop, no external API credentials required)",
            "details": {"tier": "assisted", "requires_auth": False},
        }
