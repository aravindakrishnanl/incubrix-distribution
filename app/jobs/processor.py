"""Async publish job processor.

Runs in the same process as the FastAPI application.
Job state is persisted to PostgreSQL — survives process restarts
(though in-flight jobs will need to be re-queued on restart for full reliability).
"""

from __future__ import annotations

import json
import asyncio
from app.core.logging import get_logger
from app.db.engine import get_session_factory
from app.db.models.job import JobState
from app.db.repos.jobs import JobRepository
from app.connectors.registry import get_connector
from app.core.errors import AppError, DestSpecViolationError, ErrorCode

logger = get_logger(__name__)


async def process_publish_job(job_id: str, request_body: dict) -> None:
    """Process a publish job end-to-end.

    This coroutine runs as an asyncio task. It persists state to PostgreSQL
    at each stage so GET /jobs/{job_id} reflects current progress.
    """
    import structlog
    structlog.contextvars.bind_contextvars(job_id=job_id)

    factory = get_session_factory()
    async with factory() as session:
        repo = JobRepository(session)

        try:
            # Mark running
            await repo.update_state(job_id, JobState.RUNNING, progress=5)
            await session.commit()

            connector_key = request_body.get("connector_key", "")
            rendition = request_body.get("rendition", {})
            destination = request_body.get("destination", {})
            connection = request_body.get("connection", {})
            idempotency_key = request_body.get("idempotency_key", job_id)
            destination_id = request_body.get("destination_id")
            callback_url = request_body.get("callback_url")

            # ── Resolve Destination from DB if needed ────────────────────────
            if destination_id:
                from app.db.repos.destinations import DestinationRepository
                dest_repo = DestinationRepository(session)
                dest_record = await dest_repo.get(destination_id)
                if dest_record:
                    db_dest = {
                        "id": dest_record.id,
                        "name": dest_record.name,
                        "url": dest_record.url,
                        "platform_key": dest_record.platform_key,
                        "connector_key": dest_record.connector_key,
                        "surface": dest_record.surface,
                        "category": dest_record.category,
                        "rules_url": dest_record.rules_url,
                        "frequency_cap": dest_record.frequency_cap,
                        "self_promo_allowed": dest_record.self_promo_allowed,
                        "link_policy": dest_record.link_policy,
                        "disclosure_required": dest_record.disclosure_required,
                        "automation_allowed": dest_record.automation_allowed,
                        "instance_param": dest_record.instance_param,
                        "base_url": dest_record.instance_param,
                    }
                    destination = {**db_dest, **destination}
                    if not connector_key:
                        connector_key = dest_record.connector_key

            # ── Resolve Connection & Decrypt Credentials from DB if needed ───
            from app.db.repos.connections import ConnectionRepository
            from app.services.credentials import decrypt_credentials
            conn_repo = ConnectionRepository(session)
            conn_record = None
            if connection_id := request_body.get("connection_id"):
                conn_record = await conn_repo.get(connection_id)
            elif destination_id:
                conns = await conn_repo.list_all(destination_id=destination_id)
                conn_record = conns[0] if conns else None
            if not conn_record and connector_key:
                conns = await conn_repo.list_all(connector_key=connector_key)
                conn_record = conns[0] if conns else None

            if conn_record and conn_record.encrypted_credentials:
                try:
                    decrypted = decrypt_credentials(conn_record.encrypted_credentials)
                    connection = {**decrypted, **connection}
                except Exception as exc:
                    logger.warning("conn_credential_decrypt_failed", conn_id=conn_record.id, err=str(exc))

            connector = get_connector(connector_key)
            import time
            t0 = time.perf_counter()

            # ── Rules evaluation ─────────────────────────────────────────────
            await repo.update_state(job_id, JobState.RUNNING, progress=15)
            await session.commit()

            from app.rules.engine import evaluate_rules
            rule_violations = evaluate_rules(destination, rendition, [])
            t_rules = time.perf_counter()

            # Persist rule evaluations
            from app.db.models.rule import RuleEvaluation
            from app.db.base import new_uuid

            for rv in rule_violations:
                re = RuleEvaluation(
                    id=new_uuid(),
                    job_id=job_id,
                    destination_id=destination_id or "",
                    rule_type=rv.rule_type,
                    passed=False,
                    reason=rv.message,
                )
                session.add(re)
            if not rule_violations:
                re = RuleEvaluation(
                    id=new_uuid(),
                    job_id=job_id,
                    destination_id=destination_id or "",
                    rule_type="all",
                    passed=True,
                    reason="All rules passed",
                )
                session.add(re)
            await session.commit()

            if rule_violations:
                first = rule_violations[0]
                raise AppError(first.code, first.message)

            # ── Validate with connector ───────────────────────────────────────
            await repo.update_state(job_id, JobState.RUNNING, progress=20)
            await session.commit()
            validation = await connector.validate(rendition, destination, connection)
            t_val = time.perf_counter()
            if not validation.get("ok"):
                raise DestSpecViolationError(validation.get("violations", []))

            # ── Publish ──────────────────────────────────────────────────────
            await repo.update_state(job_id, JobState.RUNNING, progress=50)
            await session.commit()
            result = await connector.publish(rendition, destination, connection, idempotency_key)
            t_pub = time.perf_counter()

            # ── Persist Publication record ────────────────────────────────────
            from app.db.models.publication import Publication
            pub = Publication(
                id=new_uuid(),
                job_id=job_id,
                destination_id=destination_id or "",
                connector_key=connector_key,
                platform_post_id=result.get("platform_post_id"),
                live_url=result.get("live_url"),
                status=result.get("status", "published"),
            )
            session.add(pub)

            # ── Persist OutputManifest (IS-9) ─────────────────────────────────
            from app.db.models.manifest import OutputManifest
            connector_manifest = getattr(connector, "manifest", None)
            connector_ver = connector_manifest.version if connector_manifest else "1.0.0"
            result_url = f"/api/v1/jobs/{job_id}/manifest"

            manifest_data = {
                "manifest_version": "1.0.0",
                "job_id": job_id,
                "connector_key": connector_key,
                "connector_version": connector_ver,
                "models_providers": [
                    {
                        "role": "connector",
                        "provider": connector_key,
                        "version": connector_ver,
                    }
                ],
                "settings": {
                    "destination_id": destination_id,
                    "simulated": result.get("_simulated", False),
                    "callback_url": callback_url,
                },
                "timings_ms": {
                    "rules_evaluation": round((t_rules - t0) * 1000, 2),
                    "validation": round((t_val - t_rules) * 1000, 2),
                    "publish": round((t_pub - t_val) * 1000, 2),
                    "total": round((t_pub - t0) * 1000, 2),
                },
                "cost_estimate_usd": 0.0,
                "warnings": [rv.message for rv in rule_violations],
                "artifacts": {
                    "platform_post_id": result.get("platform_post_id"),
                    "live_url": result.get("live_url"),
                    "result_url": result_url,
                    "assist_pack": result.get("files") or ({"deep_link": result.get("deep_link")} if result.get("deep_link") else None),
                },
                "license": {
                    "rights": "All rights reserved by author/publisher",
                    "license_type": "Author Owned",
                },
                "rendition_title": rendition.get("title"),
                "status": result.get("status", "published"),
            }
            manifest = OutputManifest(
                id=new_uuid(),
                job_id=job_id,
                manifest_json=json.dumps(manifest_data),
            )
            session.add(manifest)

            # ── Mark succeeded ────────────────────────────────────────────────
            await repo.update_state(
                job_id,
                JobState.SUCCEEDED,
                progress=100,
                platform_post_id=result.get("platform_post_id"),
                live_url=result.get("live_url"),
                result_url=result_url,
            )
            await session.commit()
            logger.info("job_succeeded", job_id=job_id, live_url=result.get("live_url"))
        except asyncio.CancelledError:
            logger.warning(
                "job_cancelled_during_processing",
                job_id=job_id,
            )
            try:
                await repo.update_state(
                    job_id,
                    JobState.FAILED,
                    progress=0,
                    error_message=(
                        "Job was cancelled during processing. "
                        "External publishing outcome may be unknown; "
                        "verify the platform before retrying."
                    ),
                )
                await session.commit()
            except Exception:
                logger.exception(
                    "job_cancellation_state_update_failed",
                    job_id=job_id,
                )
            raise
        except AppError as exc:
            try:
                await repo.update_state(
                    job_id,
                    JobState.FAILED,
                    progress=0,
                    error_code=exc.code,
                    error_message=str(exc),
                )
                await session.commit()
            except Exception:
                pass
            logger.warning("job_failed_app_error", job_id=job_id, code=exc.code)

        except Exception as exc:
            try:
                from app.core.errors import ErrorCode
                await repo.update_state(
                    job_id,
                    JobState.FAILED,
                    progress=0,
                    error_code=ErrorCode.INTERNAL_ERROR,
                    error_message=str(exc)[:500],
                )
                await session.commit()
            except Exception:
                pass
            logger.exception("job_failed_unexpected", job_id=job_id)
