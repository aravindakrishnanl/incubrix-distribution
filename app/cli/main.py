"""Command Line Interface for IncuBrix Distribution.

Usage:
    python -m app.cli publish --input content.json --destinations all --dry-run
    python -m app.cli publish --input content.json --destinations all --live
    python -m app.cli destinations
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Sequence

import httpx

from app.cli.publisher import (
    BatchReport,
    DestinationInfo,
    JobResult,
    SUPPORTED_CONNECTORS,
    execute_batch,
    fetch_destinations,
    parse_and_validate_content,
    plan_batch,
)
from app.core.settings import get_settings


def _resolve_token(cli_token: str | None) -> str:
    """Resolve API token from CLI argument, environment, or settings."""
    if cli_token and cli_token.strip():
        return cli_token.strip()

    try:
        settings_token = get_settings().api_bearer_token
        if settings_token and settings_token.strip():
            return settings_token.strip()
    except Exception:
        pass

    return ""


def _render_dry_run_plan(
    content_title: str,
    plan_items: list,
) -> None:
    print("\n" + "=" * 90)
    print("INCUBRIX PUBLISHING PLAN (DRY-RUN)")
    print("=" * 90)
    print(f"Content Title         : {content_title}")
    print(f"Destinations Selected : {len(plan_items)}")
    print("-" * 90)

    for i, item in enumerate(plan_items, 1):
        d: DestinationInfo = item.destination
        status_label = "READY (All rules passed)" if item.is_valid else "VALIDATION FAILED"
        print(f"[{i}] Destination : {d.name} ({d.connector_key})")
        print(f"    ID          : {d.id}")
        print(f"    Target URL  : {d.url or d.instance_param or 'N/A'}")
        print(f"    Idempotency : {item.idempotency_key}")
        print(f"    Status      : {status_label}")
        if item.validation_errors:
            for err in item.validation_errors:
                print(f"    * Warning/Error : {err}")
        print()

    print("=" * 90)
    print("DRY-RUN COMPLETE: Validation successful.")
    print("No publish jobs were submitted to the IncuBrix API.")
    print("Pass --live to execute actual publishing.")
    print("=" * 90 + "\n")


def _render_batch_report(report: BatchReport, content_title: str) -> None:
    print("\n" + "=" * 90)
    print("INCUBRIX UNIFIED PUBLISHING BATCH REPORT")
    print("=" * 90)
    print(f"Batch ID     : {report.batch_id}")
    print(f"Content Title: {content_title}")
    print(f"Total Dests  : {report.total_count} (Succeeded: {report.succeeded_count}, Failed: {report.failed_count})")
    print("-" * 90)

    for i, res in enumerate(report.results, 1):
        d = res.destination
        print(f"[{i}] Destination : {d.name} ({d.connector_key})")
        print(f"    ID          : {d.id}")
        print(f"    Job ID      : {res.job_id or 'N/A'}")
        print(f"    Status      : {res.display_status.upper()}")
        print(f"    Reference   : {res.formatted_reference}")
        if res.elapsed_seconds > 0:
            print(f"    Duration    : {res.elapsed_seconds}s")
        print()

    print("=" * 90)
    if report.all_succeeded:
        print(f"ALL PUBLISH JOBS SUCCEEDED ({report.succeeded_count}/{report.total_count})")
    else:
        print(f"BATCH FINISHED WITH FAILURES ({report.failed_count}/{report.total_count} failed)")
    print("=" * 90 + "\n")


async def run_publish(args: argparse.Namespace) -> int:
    # 1. Resolve authentication
    token = _resolve_token(args.token)
    if not token:
        print(
            "ERROR: API Bearer Token is required.\n"
            "Provide --token <token> or configure API_BEARER_TOKEN in your environment or .env file.",
            file=sys.stderr,
        )
        return 1

    # 2. Determine mode
    is_live = bool(args.live)
    is_dry_run = bool(args.dry_run)

    if is_live and is_dry_run:
        print("ERROR: --live and --dry-run are mutually exclusive. Choose one.", file=sys.stderr)
        return 1

    if not is_live and not is_dry_run:
        # Default safely to dry-run
        is_dry_run = True
        print("[NOTICE] Neither --live nor --dry-run specified; defaulting safely to DRY-RUN mode.")

    # 3. Read and validate content
    try:
        rendition = parse_and_validate_content(args.input)
    except Exception as exc:
        print(f"ERROR reading content file: {exc}", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=args.timeout + 10) as client:
        # 4. Fetch destination catalogue
        try:
            destinations = await fetch_destinations(client, args.destinations)
        except PermissionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERROR resolving destinations: {exc}", file=sys.stderr)
            return 1

        if not destinations:
            print("ERROR: No matching active destinations found in catalogue.", file=sys.stderr)
            return 1

        # 5. Build planned batch
        batch_id = f"batch-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        plan = plan_batch(destinations, rendition, batch_id)

        # 6. Execute based on mode
        if is_dry_run:
            _render_dry_run_plan(rendition["title"], plan)
            return 0

        # Live publishing mode
        print("\n" + "!" * 90)
        print("[LIVE PUBLISHING WARNING]")
        print("  --live flag specified. Submitting actual publish jobs to IncuBrix API.")
        print("  Note: Server SIMULATION_MODE setting governs whether live external APIs are dispatched.")
        print("!" * 90 + "\n")

        report = await execute_batch(
            client=client,
            plan=plan,
            rendition=rendition,
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout,
        )

        _render_batch_report(report, rendition["title"])

        if args.output:
            out_path = Path(args.output)
            out_data = {
                "batch_id": report.batch_id,
                "total_count": report.total_count,
                "succeeded_count": report.succeeded_count,
                "failed_count": report.failed_count,
                "results": [
                    {
                        "destination_id": r.destination.id,
                        "destination_name": r.destination.name,
                        "connector_key": r.destination.connector_key,
                        "job_id": r.job_id,
                        "status": r.status,
                        "display_status": r.display_status,
                        "platform_post_id": r.platform_post_id,
                        "live_url": r.live_url,
                        "error_code": r.error_code,
                        "error_message": r.error_message,
                        "elapsed_seconds": r.elapsed_seconds,
                    }
                    for r in report.results
                ],
            }
            out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
            print(f"Wrote consolidated JSON report to: {out_path.resolve()}")

        return 0 if report.all_succeeded else 1


async def run_list_destinations(args: argparse.Namespace) -> int:
    token = _resolve_token(args.token)
    if not token:
        print("ERROR: API Bearer Token required. Configure API_BEARER_TOKEN or pass --token.", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=15) as client:
            dests = await fetch_destinations(client, ["all"])
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # Graceful offline / direct database query fallback
        try:
            from app.db.engine import get_session_factory
            from app.db.repos.destinations import DestinationRepository
            factory = get_session_factory()
            async with factory() as session:
                repo = DestinationRepository(session)
                db_dests = await repo.list_all(active=True)
                dests = [
                    DestinationInfo.from_api_dict({
                        "id": d.id,
                        "name": d.name,
                        "connector_key": d.connector_key,
                        "platform_key": d.platform_key,
                        "url": d.url,
                        "category": d.category,
                        "rules_url": d.rules_url,
                        "frequency_cap": d.frequency_cap,
                        "self_promo_allowed": d.self_promo_allowed,
                        "link_policy": d.link_policy,
                        "disclosure_required": d.disclosure_required,
                        "automation_allowed": d.automation_allowed,
                        "instance_param": d.instance_param,
                        "active": d.active,
                    })
                    for d in db_dests
                ]
        except Exception as db_exc:
            print(f"ERROR: Could not connect to API server at {base_url} and direct database query failed: {db_exc}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nConfigured Active Destinations ({len(dests)} total):")
    print("-" * 90)
    for d in dests:
        print(f"ID: {d.id:<36} | {d.connector_key:<12} | {d.name:<25} | {d.url or ''}")
    print("-" * 90 + "\n")
    return 0


async def run_seed_command(args: argparse.Namespace) -> int:
    from app.db.engine import get_session_factory
    from app.services.catalogue_seed import seed_catalogue_and_connections

    print("\n" + "=" * 80)
    print("INCUBRIX DISTRIBUTION — SEEDING CATALOGUE & CONNECTIONS")
    print("=" * 80)

    factory = get_session_factory()
    async with factory() as session:
        result = await seed_catalogue_and_connections(session)

        print(f"Destinations: {len(result.destinations_created)} created, {len(result.destinations_updated)} updated ({result.total_destinations} total)")
        for d in result.destinations_created:
            print(f"  [+] Created: {d.name} ({d.connector_key}) -> {d.url}")
        for d in result.destinations_updated:
            print(f"  [*] Updated: {d.name} ({d.connector_key}) -> {d.url}")

        print(f"\nConnections : {len(result.connections_created)} created, {len(result.connections_updated)} updated ({result.total_connections} total)")
        for c in result.connections_created:
            print(f"  [+] Created: {c.label} ({c.connector_key})")
        for c in result.connections_updated:
            print(f"  [*] Updated: {c.label} ({c.connector_key})")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  [!] {w}")

        print("=" * 80 + "\n")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="IncuBrix Distribution Unified Publishing CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── publish subcommand ──────────────────────────────────────────────────
    pub_parser = subparsers.add_parser("publish", help="Publish content to configured destinations")
    pub_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the content JSON file (containing title, body, tags, etc.)",
    )
    pub_parser.add_argument(
        "--destinations", "-d",
        required=True,
        nargs="+",
        help="Destination selector: 'all' or explicit destination IDs (comma or space separated)",
    )
    pub_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate and validate the publish plan without submitting any jobs (safe default)",
    )
    pub_parser.add_argument(
        "--live",
        action="store_true",
        help="Execute real publishing jobs through the IncuBrix API",
    )
    pub_parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="IncuBrix API base URL (default: http://localhost:8000)",
    )
    pub_parser.add_argument(
        "--token",
        default="",
        help="API Bearer Token (defaults to API_BEARER_TOKEN from .env/environment)",
    )
    pub_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Maximum seconds to wait for jobs to finish (default: 60.0s)",
    )
    pub_parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds between polling queries (default: 1.0s)",
    )
    pub_parser.add_argument(
        "--output", "-o",
        help="Optional path to output the consolidated JSON report",
    )

    # ── destinations subcommand ─────────────────────────────────────────────
    dest_parser = subparsers.add_parser("destinations", help="List active destinations from the catalogue")
    dest_parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="IncuBrix API base URL (default: http://localhost:8000)",
    )
    dest_parser.add_argument(
        "--token",
        default="",
        help="API Bearer Token (defaults to API_BEARER_TOKEN from .env/environment)",
    )

    # ── seed subcommand ─────────────────────────────────────────────────────
    subparsers.add_parser("seed", help="Initialize or update catalogue destinations and connections")

    return parser


async def async_cli_entrypoint(argv: Sequence[str] | None = None) -> int:
    """Asynchronous CLI entrypoint for testing and embedding."""
    raw_args = list(argv if argv is not None else sys.argv[1:])

    # User convenience: if invoked with --input directly without subcommand 'publish', auto-route to publish
    if raw_args and not raw_args[0].startswith("-") and raw_args[0] not in ("publish", "destinations", "seed", "help"):
        pass
    elif raw_args and raw_args[0].startswith("--input") or ("-i" in raw_args and "publish" not in raw_args):
        raw_args.insert(0, "publish")

    parser = build_parser()
    if not raw_args:
        parser.print_help()
        return 0

    parsed = parser.parse_args(raw_args)

    if parsed.command == "publish":
        return await run_publish(parsed)
    elif parsed.command == "destinations":
        return await run_list_destinations(parsed)
    elif parsed.command == "seed":
        return await run_seed_command(parsed)
    else:
        parser.print_help()
        return 0


def cli_entrypoint(argv: Sequence[str] | None = None) -> int:
    """Synchronous CLI entrypoint."""
    return asyncio.run(async_cli_entrypoint(argv))


if __name__ == "__main__":
    sys.exit(cli_entrypoint())
