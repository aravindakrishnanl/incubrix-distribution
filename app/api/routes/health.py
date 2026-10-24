"""Health and readiness endpoints.

GET /health  — process-level liveness (always returns 200 if the process is up)
GET /ready   — dependency readiness (PostgreSQL + storage)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.engine import get_db_session
from app.core.settings import get_settings

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def health() -> dict:
    """Process liveness — always 200 if the app is running."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
    }


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db_session)) -> dict:
    """Dependency readiness — checks PostgreSQL and storage."""
    checks: dict[str, str] = {}

    # ── PostgreSQL check ──────────────────────────────────────────────────────
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.warning("readiness_check_postgres_failed", error=str(exc))
        checks["postgres"] = f"error: {exc}"

    # ── Storage check ─────────────────────────────────────────────────────────
    try:
        from app.storage.factory import get_storage
        storage = get_storage()
        await storage.health_check()
        checks["storage"] = "ok"
    except Exception as exc:
        logger.warning("readiness_check_storage_failed", error=str(exc))
        checks["storage"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    status_code = 200 if overall == "ok" else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
