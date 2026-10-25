
"""Assisted Publishing connector.

Builds a ready-to-post pack for human posting.
Packs are stored locally and can be retrieved through the returned pack path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.connectors.base import BaseConnector
from app.core.logging import get_logger

logger = get_logger(__name__)

PACKS_DIR = Path("artifacts") / "assisted"


class AssistedConnector(BaseConnector):
    key = "assisted"
    version = "1.0.0"
    tier = "assisted"
    auth = "none"

    async def validate(self, rendition, destination, connection) -> dict[str, Any]:
        violations = []
        if not rendition.get("title"):
            violations.append({
                "field": "title",
                "message": "title is required for assisted pack",
            })
        return {"ok": not violations, "violations": violations}

    async def publish(
        self, rendition, destination, connection, idempotency_key
    ) -> dict[str, Any]:
        pack = await self.build_assist_pack(rendition, destination)

        PACKS_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(idempotency_key))
        pack_path = PACKS_DIR / f"{safe_id}.json"
        pack_path.write_text(
            json.dumps(pack, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        markdown = next(
            (item["content"] for item in pack["files"]
             if item["name"] == "post.md"),
            "",
        )
        markdown_path = PACKS_DIR / f"{safe_id}.md"
        markdown_path.write_text(markdown, encoding="utf-8")

        logger.info(
            "assisted_pack_saved",
            pack_id=safe_id,
            file_count=len(pack["files"]),
        )

        return {
            "platform_post_id": f"assisted:{safe_id}",
            "live_url": None,
            "status": "assist_ready",
            "pack_path": str(pack_path.resolve()),
            "markdown_path": str(markdown_path.resolve()),
            "destination_url": pack["destination_url"],
            "checklist": pack["checklist"],
        }

    async def get_status(self, platform_post_id, connection) -> dict[str, Any]:
        return {"status": "assist_ready", "live_url": None}

    async def delete(self, platform_post_id, connection) -> dict[str, Any]:
        return {"deleted": True}

    async def build_assist_pack(self, rendition, destination) -> dict[str, Any]:
        title = rendition.get("title", "")
        body = rendition.get("body", "")
        rules_url = destination.get("rules_url") or destination.get("url", "")
        dest_url = destination.get("url", "")

        checklist = [
            {
                "check": "Read destination rules before posting",
                "url": rules_url,
                "required": True,
            },
            {
                "check": "Verify the title and content",
                "required": True,
            },
            {
                "check": "Disclose AI-generated content if required",
                "required": bool(destination.get("disclosure_required", False)),
            },
            {
                "check": "Verify self-promotion is allowed",
                "required": not destination.get("self_promo_allowed", True),
            },
            {
                "check": "Check the destination's posting frequency cap",
                "required": bool(destination.get("frequency_cap")),
            },
        ]

        files = [{
            "name": "post.md",
            "content_type": "text/markdown",
            "content": f"# {title}\n\n{body}",
        }]

        for i, img in enumerate(rendition.get("images", []), start=1):
            files.append({
                "name": f"image_{i}",
                "content_type": "image/*",
                "url": img,
            })

        return {
            "title": title,
            "destination_name": destination.get("name", "Unknown destination"),
            "destination_url": dest_url,
            "deep_link": dest_url,
            "rules_url": rules_url,
            "caption": body[:300] + ("..." if len(body) > 300 else ""),
            "files": files,
            "checklist": checklist,
            "instructions": [
                "Open the destination URL.",
                "Review the destination rules and checklist.",
                "Copy the content from the Markdown file.",
                "Publish manually and verify the resulting post.",
            ],
        }

    async def check_connectivity(
        self,
        connection: dict[str, Any],
        destination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Assisted publishing is ready; posting requires a human.",
            "details": {"tier": "assisted", "requires_auth": False},
        }
