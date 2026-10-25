"""Safe, repeatable catalogue initialization script for IncuBrix Distribution.

Usage:
    python scripts/seed_catalogue.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.engine import get_session_factory
from app.services.catalogue_seed import seed_catalogue_and_connections


async def run_seed() -> int:
    print("\n" + "=" * 70)
    print("INCUBRIX DISTRIBUTION — DESTINATION CATALOGUE INITIALIZATION")
    print("=" * 70)

    factory = get_session_factory()
    async with factory() as session:
        result = await seed_catalogue_and_connections(session)

        print(f"\nDestinations : {len(result.destinations_created)} created, {len(result.destinations_updated)} updated")
        for d in result.destinations_created:
            print(f"  [+] Created Destination: {d.name} ({d.connector_key}) -> {d.url}")
        for d in result.destinations_updated:
            print(f"  [*] Updated Destination: {d.name} ({d.connector_key}) -> {d.url}")

        print(f"\nConnections  : {len(result.connections_created)} created, {len(result.connections_updated)} updated")
        for c in result.connections_created:
            print(f"  [+] Created Connection: {c.label} ({c.connector_key})")
        for c in result.connections_updated:
            print(f"  [*] Updated Connection: {c.label} ({c.connector_key})")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  [!] {w}")

        print("\n" + "=" * 70)
        print("Initialization completed successfully. No plaintext secrets stored or printed.")
        print("=" * 70 + "\n")
        return 0


def main() -> None:
    code = asyncio.run(run_seed())
    sys.exit(code)


if __name__ == "__main__":
    main()
