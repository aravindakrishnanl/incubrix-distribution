"""Job management routes.

POST /api/v1/publish  → 202 + job_id
GET  /api/v1/jobs/{job_id} → job status/progress/result
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import IdempotencyConflictError, AppError, ErrorCode
from app.core.logging import get_logger
from app.core.security import require_bearer_token
from app.db.engine import get_db_session
from app.db.models.idempotency import IdempotencyRecord
from app.db.models.job import PublishJob, JobState
from app.db.repos.jobs import JobRepository
from app.db.repos.idempotency import IdempotencyRepository

router = APIRouter(prefix="/api/v1", tags=["jobs"])
logger = get_logger(__name__)


def _fingerprint(idempotency_key: str, body: dict) -> str:
    """SHA-256 hash of the idempotency key + canonical JSON of the body."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=True)
    data = f"{idempotency_key}:{canonical}".encode()
    return hashlib.sha256(data).hexdigest()


@router.post("/publish", status_code=202)
async def submit_publish(
    request_body: dict,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Submit a publish job.

    Requires Idempotency-Key header. Returns 202 with job_id immediately.
    The connector invocation runs asynchronously.
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required.",
        )

    fingerprint = _fingerprint(idempotency_key, request_body)
    idem_repo = IdempotencyRepository(db)
    job_repo = JobRepository(db)

    # ── Check existing idempotency record ─────────────────────────────────────
    existing = await idem_repo.find(idempotency_key)
    if existing:
        if existing.fingerprint != fingerprint:
            raise IdempotencyConflictError(idempotency_key)
        # Same key + same payload → return original job
        job = await job_repo.get(existing.job_id) if existing.job_id else None
        if job:
            logger.info("idempotency_replay", idempotency_key=idempotency_key, job_id=job.id)
            return _job_response(job)

    # ── Create new job ─────────────────────────────────────────────────────────
    job = await job_repo.create(
        connector_key=request_body.get("connector_key"),
        destination_id=request_body.get("destination_id"),
        idempotency_key=idempotency_key,
        callback_url=request_body.get("callback_url"),
    )
    await idem_repo.create(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        job_id=job.id,
    )

    # ── Dispatch async (fire and forget in same process for assessment) ────────
    import asyncio
    from app.jobs.processor import process_publish_job
    asyncio.create_task(process_publish_job(job.id, request_body))

    logger.info("publish_job_created", job_id=job.id, idempotency_key=idempotency_key)
    return _job_response(job)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get the status and result of a publish job."""
    job_repo = JobRepository(db)
    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return _job_response(job)


@router.get("/jobs/{job_id}/manifest")
async def get_job_manifest(
    job_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get the machine-readable output manifest (IS-9) for a job."""
    from sqlalchemy import select
    from app.db.models.manifest import OutputManifest

    job_repo = JobRepository(db)
    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")

    res = await db.execute(select(OutputManifest).where(OutputManifest.job_id == job_id))
    manifest = res.scalar_one_or_none()
    if not manifest or not manifest.manifest_json:
        raise HTTPException(status_code=404, detail="Manifest not found for job.")
    return json.loads(manifest.manifest_json)


@router.get("/jobs/{job_id}/result")
async def get_job_result(
    job_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get job result details."""
    job_repo = JobRepository(db)
    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return {
        "job_id": job.id,
        "status": job.state,
        "platform_post_id": job.platform_post_id,
        "live_url": job.live_url,
        "result_url": job.result_url or f"/api/v1/jobs/{job.id}/manifest",
    }


def _job_response(job: PublishJob) -> dict:
    resp = {
        "job_id": job.id,
        "status": job.state,
        "progress": job.progress,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
    if job.state == JobState.SUCCEEDED:
        resp["result"] = {
            "platform_post_id": job.platform_post_id,
            "live_url": job.live_url,
            "result_url": job.result_url or f"/api/v1/jobs/{job.id}/manifest",
        }
    if job.state == JobState.FAILED:
        resp["error"] = {
            "code": job.error_code,
            "message": job.error_message,
        }
    return resp
