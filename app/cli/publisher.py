"""Publishing orchestration engine for the IncuBrix CLI.

Reuses the existing authenticated IncuBrix API endpoints:
- GET  /api/v1/destinations
- POST /api/v1/publish
- GET  /api/v1/jobs/{job_id}
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.rules.engine import evaluate_rules


SUPPORTED_CONNECTORS = {
    "discourse",
    "lemmy",
    "devto",
    "ghost",
    "webhook_hmac",
    "assisted",
}


@dataclass
class DestinationInfo:
    id: str
    name: str
    connector_key: str
    url: str | None = None
    platform_key: str | None = None
    category: str | None = None
    rules_url: str | None = None
    frequency_cap: str | None = None
    self_promo_allowed: bool | None = None
    link_policy: str | None = None
    disclosure_required: bool | None = None
    automation_allowed: bool | None = None
    instance_param: str | None = None
    active: bool = True

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> DestinationInfo:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Unnamed"),
            connector_key=data.get("connector_key", "unknown"),
            url=data.get("url"),
            platform_key=data.get("platform_key"),
            category=data.get("category"),
            rules_url=data.get("rules_url"),
            frequency_cap=data.get("frequency_cap"),
            self_promo_allowed=data.get("self_promo_allowed"),
            link_policy=data.get("link_policy"),
            disclosure_required=data.get("disclosure_required"),
            automation_allowed=data.get("automation_allowed"),
            instance_param=data.get("instance_param"),
            active=bool(data.get("active", True)),
        )

    def to_rule_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "platform_key": self.platform_key,
            "connector_key": self.connector_key,
            "rules_url": self.rules_url,
            "frequency_cap": self.frequency_cap,
            "self_promo_allowed": self.self_promo_allowed,
            "link_policy": self.link_policy,
            "disclosure_required": self.disclosure_required,
            "automation_allowed": self.automation_allowed,
            "instance_param": self.instance_param,
        }


@dataclass
class PublishPlanItem:
    destination: DestinationInfo
    idempotency_key: str
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class JobResult:
    destination: DestinationInfo
    idempotency_key: str
    job_id: str | None = None
    status: str = "pending"  # succeeded | failed | timeout | http_error | skipped
    progress: int = 0
    platform_post_id: str | None = None
    live_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def display_status(self) -> str:
        if self.status == "succeeded":
            if self.destination.connector_key == "assisted":
                return "assist_ready"
            elif self.destination.connector_key == "webhook_hmac":
                return "delivered"
            return "published"
        return self.status

    @property
    def formatted_reference(self) -> str:
        conn = self.destination.connector_key
        if self.status == "succeeded":
            if conn == "assisted":
                link = self.live_url or self.destination.url or "N/A"
                return f"[Assisted Pack Ready] Submission Link: {link} (Human post required - not publicly published)"
            elif conn == "webhook_hmac":
                link = self.live_url or self.destination.url or "N/A"
                return f"[Webhook Delivered] Endpoint: {link}"
            else:
                link = self.live_url or "N/A"
                return f"[Public URL] {link}"
        elif self.error_message:
            return f"[{self.error_code or 'ERROR'}] {self.error_message}"
        return "N/A"


@dataclass
class BatchReport:
    batch_id: str
    is_dry_run: bool
    total_count: int
    succeeded_count: int
    failed_count: int
    results: list[JobResult]

    @property
    def all_succeeded(self) -> bool:
        return self.failed_count == 0


def parse_and_validate_content(content_path: str | Path) -> dict[str, Any]:
    """Read and validate the content JSON file."""
    path = Path(content_path)
    if not path.is_file():
        raise FileNotFoundError(f"Content file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in content file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Content file must contain a JSON object at root, got {type(data).__name__}")

    # Support both {"rendition": {...}} and flat {"title": ..., "body": ...}
    if "rendition" in data and isinstance(data["rendition"], dict):
        rendition = data["rendition"]
    else:
        rendition = data

    title = rendition.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        raise ValueError("Content validation failed: 'title' is required and must be a non-empty string.")

    body = rendition.get("body")
    if body is not None and not isinstance(body, str):
        raise ValueError("Content validation failed: 'body' must be a string if provided.")

    return rendition


async def fetch_destinations(
    client: httpx.AsyncClient,
    selector: list[str],
) -> list[DestinationInfo]:
    """Fetch and filter destinations from the IncuBrix API."""
    resp = await client.get("/api/v1/destinations", params={"limit": 500})
    if resp.status_code == 401:
        raise PermissionError("API authentication failed: Invalid or missing API Bearer token.")
    if not resp.is_success:
        raise RuntimeError(f"Failed to fetch destinations: HTTP {resp.status_code} {resp.text[:200]}")

    data = resp.json()
    items = data.get("items") or data.get("destinations") or []
    all_destinations = [DestinationInfo.from_api_dict(item) for item in items]

    is_all = any(s.strip().lower() == "all" for s in selector)
    if is_all:
        # Return all active destinations
        active_dests = [d for d in all_destinations if d.active]
        return active_dests

    # Normalize specific IDs from arguments (support comma-separated or space-separated)
    target_ids = set()
    for s in selector:
        for piece in s.split(","):
            cleaned = piece.strip()
            if cleaned and cleaned.lower() != "all":
                target_ids.add(cleaned)

    selected: list[DestinationInfo] = []
    dest_by_id = {d.id: d for d in all_destinations}

    for tid in target_ids:
        if tid in dest_by_id:
            selected.append(dest_by_id[tid])
        else:
            # Try fetching individually
            single_resp = await client.get(f"/api/v1/destinations/{tid}")
            if single_resp.status_code == 200:
                dest = DestinationInfo.from_api_dict(single_resp.json())
                selected.append(dest)
            else:
                raise ValueError(f"Destination with ID '{tid}' was not found in the catalogue.")

    return selected


def plan_batch(
    destinations: list[DestinationInfo],
    rendition: dict[str, Any],
    batch_id: str,
) -> list[PublishPlanItem]:
    """Build deterministic publish plan items and evaluate rules for each destination."""
    plan: list[PublishPlanItem] = []

    for dest in destinations:
        # Deterministic, unique idempotency key per batch and destination
        idempotency_key = f"{batch_id}-{dest.id}"
        errors: list[str] = []

        # 1. Check connector key
        if dest.connector_key not in SUPPORTED_CONNECTORS:
            errors.append(f"Unsupported connector key: '{dest.connector_key}'")

        # 2. Evaluate destination rules against rendition
        rule_violations = evaluate_rules(dest.to_rule_dict(), rendition, [])
        for rv in rule_violations:
            errors.append(f"Rule violation [{rv.code}]: {rv.message}")

        plan.append(
            PublishPlanItem(
                destination=dest,
                idempotency_key=idempotency_key,
                is_valid=(len(errors) == 0),
                validation_errors=errors,
            )
        )

    return plan


async def _poll_single_job(
    client: httpx.AsyncClient,
    job_id: str,
    result: JobResult,
    timeout_seconds: float,
    poll_interval: float,
) -> None:
    """Poll a single job until terminal state or timeout."""
    start_time = time.perf_counter()
    deadline = start_time + timeout_seconds

    while time.perf_counter() < deadline:
        try:
            resp = await client.get(f"/api/v1/jobs/{job_id}")
            if resp.status_code == 401:
                result.status = "http_error"
                result.error_code = "AUTH_FAILED"
                result.error_message = "Authentication expired or invalid token during polling."
                return
            if not resp.is_success:
                result.status = "http_error"
                result.error_code = f"HTTP_{resp.status_code}"
                result.error_message = f"Error polling job {job_id}: HTTP {resp.status_code}"
                return

            job_data = resp.json()
            state = job_data.get("status") or job_data.get("state")
            result.progress = int(job_data.get("progress", 0))

            if state == "succeeded":
                result.status = "succeeded"
                res = job_data.get("result", {})
                result.platform_post_id = res.get("platform_post_id") or job_data.get("platform_post_id")
                result.live_url = res.get("live_url") or job_data.get("live_url")
                result.elapsed_seconds = round(time.perf_counter() - start_time, 2)
                return

            if state == "failed":
                result.status = "failed"
                err = job_data.get("error", {})
                result.error_code = err.get("code") or job_data.get("error_code") or "JOB_FAILED"
                result.error_message = err.get("message") or job_data.get("error_message") or "Publish job failed."
                result.elapsed_seconds = round(time.perf_counter() - start_time, 2)
                return

            # Still in-flight (queued / running)
            await asyncio.sleep(poll_interval)

        except httpx.RequestError as exc:
            # Network blip during polling, wait and retry unless deadline passed
            await asyncio.sleep(poll_interval)

    # Deadline exceeded
    result.status = "timeout"
    result.error_code = "POLLING_TIMEOUT"
    result.error_message = f"Job {job_id} did not finish within {timeout_seconds} seconds."
    result.elapsed_seconds = round(time.perf_counter() - start_time, 2)


async def execute_batch(
    client: httpx.AsyncClient,
    plan: list[PublishPlanItem],
    rendition: dict[str, Any],
    poll_interval: float = 1.0,
    timeout_seconds: float = 60.0,
) -> BatchReport:
    """Submit publish jobs for each planned destination and poll concurrently."""
    batch_id = plan[0].idempotency_key.split("-")[0] if plan else f"batch-{uuid.uuid4().hex[:8]}"
    results: list[JobResult] = []
    active_poll_tasks = []

    for item in plan:
        dest = item.destination
        job_res = JobResult(destination=dest, idempotency_key=item.idempotency_key)

        if not item.is_valid:
            job_res.status = "skipped"
            job_res.error_code = "VALIDATION_FAILED"
            job_res.error_message = "; ".join(item.validation_errors)
            results.append(job_res)
            continue

        payload = {
            "connector_key": dest.connector_key,
            "destination_id": dest.id,
            "rendition": rendition,
        }

        try:
            submit_resp = await client.post(
                "/api/v1/publish",
                json=payload,
                headers={"Idempotency-Key": item.idempotency_key},
            )
            if submit_resp.status_code == 202:
                job_id = submit_resp.json().get("job_id")
                job_res.job_id = job_id
                job_res.status = "running"
                results.append(job_res)
                active_poll_tasks.append(
                    _poll_single_job(
                        client=client,
                        job_id=job_id,
                        result=job_res,
                        timeout_seconds=timeout_seconds,
                        poll_interval=poll_interval,
                    )
                )
            else:
                job_res.status = "http_error"
                job_res.error_code = f"HTTP_{submit_resp.status_code}"
                try:
                    err_json = submit_resp.json()
                    job_res.error_message = err_json.get("error", {}).get("message") or submit_resp.text[:200]
                except Exception:
                    job_res.error_message = submit_resp.text[:200]
                results.append(job_res)

        except Exception as exc:
            job_res.status = "http_error"
            job_res.error_code = "NETWORK_ERROR"
            job_res.error_message = str(exc)
            results.append(job_res)

    # Concurrently poll all submitted jobs
    if active_poll_tasks:
        await asyncio.gather(*active_poll_tasks, return_exceptions=True)

    succeeded = sum(1 for r in results if r.status == "succeeded")
    failed = len(results) - succeeded

    return BatchReport(
        batch_id=batch_id,
        is_dry_run=False,
        total_count=len(results),
        succeeded_count=succeeded,
        failed_count=failed,
        results=results,
    )
