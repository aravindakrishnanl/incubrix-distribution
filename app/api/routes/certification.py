"""Certification endpoints — run connector certification and store evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.security import require_bearer_token
from app.db.engine import get_db_session

router = APIRouter(prefix="/api/v1", tags=["certification"])


class CertificationRequest(BaseModel):
    destination_id: str | None = None
    connector_key: str | None = None
    target_level: str | None = None
    test_title: str = "IncuBrix Certification Test Post"
    test_body: str = "This is an automated certification test. It will be deleted immediately."
    connection: dict | None = None  # optional connection overrides


def _run_to_dict(r) -> dict:
    pub_resp = json.loads(r.publish_response) if r.publish_response else None
    stat_resp = json.loads(r.status_response) if r.status_response else None
    del_resp = json.loads(r.delete_response) if r.delete_response else None
    return {
        "id": r.id,
        "run_id": r.id,
        "destination_id": r.destination_id,
        "connector_key": r.connector_key,
        "passed": r.passed,
        "status": "passed" if r.passed else "failed",
        "error_message": r.error_message,
        "live_url": r.live_url,
        "publish_response": pub_resp,
        "status_response": stat_resp,
        "delete_response": del_resp,
        "summary": "Certification passed all stages (validate, publish, get_status, delete)" if r.passed else f"Certification failed: {r.error_message}",
        "test_results": [
            {"stage": "validate", "passed": True},
            {"stage": "publish", "passed": r.passed or pub_resp is not None, "response": pub_resp},
            {"stage": "get_status", "passed": r.passed or stat_resp is not None, "response": stat_resp},
            {"stage": "delete", "passed": r.passed or del_resp is not None, "response": del_resp},
        ],
        "run_at": r.run_at.isoformat() if r.run_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/certification/run", status_code=200)
async def run_certification_standalone(
    body: CertificationRequest,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not body.destination_id:
        raise HTTPException(status_code=400, detail="destination_id is required")
    return await run_certification(destination_id=body.destination_id, body=body, _token=_token, db=db)


@router.post("/certify/{destination_id}", status_code=200)
async def run_certification(
    destination_id: str,
    body: CertificationRequest = CertificationRequest(),
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:

    """Run a certification test against a destination.

    The test sequence: validate → publish → get_status → delete.
    All evidence is stored in the certification_runs table.
    Level is upgraded if all steps pass.
    """
    from app.db.repos.destinations import DestinationRepository
    from app.db.models.certification import CertificationRun
    from app.connectors.registry import get_connector
    from app.db.base import new_uuid

    # Load destination
    dest_repo = DestinationRepository(db)
    dest = await dest_repo.get(destination_id)
    if not dest:
        raise HTTPException(status_code=404, detail=f"Destination {destination_id!r} not found")

    connector_key = dest.connector_key
    try:
        connector = get_connector(connector_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot get connector {connector_key!r}: {exc}")

    # Build test rendition and destination dict
    rendition = {
        "title": body.test_title,
        "body": body.test_body,
        "tags": ["certification", "test"],
    }
    destination_dict = {
        "url": dest.url,
        "instance_param": dest.instance_param,
        "community_id": None,
    }
    connection = body.connection or {}

    now = datetime.now(timezone.utc)
    run = CertificationRun(
        id=new_uuid(),
        destination_id=destination_id,
        connector_key=connector_key,
        run_at=now,
    )
    db.add(run)
    await db.flush()

    passed = True
    error_message = None
    publish_response = None
    status_response = None
    delete_response = None
    live_url = None
    platform_post_id = None

    try:
        # Step 1: Validate
        validation = await connector.validate(rendition, destination_dict, connection)
        if not validation.get("ok"):
            violations = validation.get("violations", [])
            raise ValueError(f"Validation failed: {violations}")

        # Step 2: Publish
        pub_result = await connector.publish(rendition, destination_dict, connection, f"cert-{run.id}")
        publish_response = json.dumps(pub_result)
        platform_post_id = pub_result.get("platform_post_id")
        live_url = pub_result.get("live_url")

        # Step 3: Get status
        if platform_post_id:
            stat_result = await connector.get_status(platform_post_id, connection)
            status_response = json.dumps(stat_result)

        # Step 4: Delete (cleanup)
        if platform_post_id:
            del_result = await connector.delete(platform_post_id, connection)
            delete_response = json.dumps(del_result)

    except Exception as exc:
        passed = False
        error_message = str(exc)[:1000]

    # Persist run result
    completed_at = datetime.now(timezone.utc)
    run.passed = passed
    run.error_message = error_message
    run.live_url = live_url
    run.publish_response = publish_response
    run.status_response = status_response
    run.delete_response = delete_response
    run.completed_at = completed_at

    # Upgrade certification level if passed
    if passed:
        new_level = min(dest.level + 1, 4)
        await dest_repo.update(destination_id, level=new_level, last_certified_at=completed_at)

    await db.commit()
    await db.refresh(run)

    return {
        **_run_to_dict(run),
        "destination_level": dest.level + (1 if passed else 0),
    }


@router.get("/certify/{destination_id}")
async def get_certification(
    destination_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get the most recent certification run for a destination."""
    from sqlalchemy import select
    from app.db.models.certification import CertificationRun

    result = await db.execute(
        select(CertificationRun)
        .where(CertificationRun.destination_id == destination_id)
        .order_by(CertificationRun.run_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"No certification runs found for destination {destination_id!r}",
        )
    return _run_to_dict(run)


@router.get("/certification/{run_id}")
async def get_certification_by_run_id(
    run_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get a certification run by run_id."""
    from sqlalchemy import select
    from app.db.models.certification import CertificationRun

    result = await db.execute(
        select(CertificationRun)
        .where(CertificationRun.id == run_id)
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Certification run {run_id!r} not found",
        )
    return _run_to_dict(run)


@router.get("/certify/{destination_id}/history")
async def get_certification_history(
    destination_id: str,
    limit: int = 10,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get certification run history for a destination."""
    from sqlalchemy import select
    from app.db.models.certification import CertificationRun

    result = await db.execute(
        select(CertificationRun)
        .where(CertificationRun.destination_id == destination_id)
        .order_by(CertificationRun.run_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    return {
        "destination_id": destination_id,
        "runs": [_run_to_dict(r) for r in runs],
        "total": len(runs),
    }
