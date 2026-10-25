"""Publish an existing Ghost draft post by its platform_post_id.

Usage:
    python scripts/publish_ghost_draft.py <platform_post_id> [--live]

Requirements enforced:
1. Reuses Ghost Admin API JWT signing and configured credentials (never prints API keys).
2. Fetches existing post first to obtain current 'updated_at' timestamp.
3. Confirms post title matches '[TEST DRAFT] IncuBrix Ghost Integration Verification'.
4. Updates post via PUT /ghost/api/admin/posts/{id}/ with updated_at and status='published'.
5. Prints resulting status and public URL without creating any new post.
6. Does not alter default SIMULATION_MODE.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.connectors.registry import get_connector, init_registry
from app.core.errors import AppError
from app.core.settings import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely publish a verified Ghost draft post by its platform_post_id.",
    )
    parser.add_argument(
        "platform_post_id",
        help="The platform_post_id (Ghost post ID) of the draft to publish.",
    )
    parser.add_argument(
        "--expected-title",
        default="[TEST DRAFT] IncuBrix Ghost Integration Verification",
        help="Expected title of the post (default: '[TEST DRAFT] IncuBrix Ghost Integration Verification').",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute against live Ghost Admin API (bypasses default SIMULATION_MODE).",
    )

    args = parser.parse_args()

    init_registry()
    connector = get_connector("ghost")

    settings = get_settings()
    is_live = args.live or not settings.simulation_mode

    print(f"Target Ghost Post ID: {args.platform_post_id}")
    print(f"Expected Title      : {args.expected_title}")
    print(f"Execution Mode      : {'LIVE' if is_live else 'SIMULATION'}")

    try:
        result = await connector.publish_draft(
            platform_post_id=args.platform_post_id,
            expected_title=args.expected_title,
            force_live=args.live,
        )
    except AppError as err:
        print(f"ERROR [{err.code}]: {err.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    status = result.get("status")
    public_url = result.get("live_url") or result.get("url") or "N/A"
    simulated = result.get("_simulated", False)

    print("\nResult:")
    print(f"Status    : {status}")
    print(f"Public URL: {public_url}")
    if simulated:
        print("\nNote: Ran in SIMULATION mode. Pass --live to perform actual live publication.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
