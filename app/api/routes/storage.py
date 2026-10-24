"""Storage info route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_bearer_token
from app.core.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["storage"])


@router.get("/storage")
async def storage_info(
    _token: str = Depends(require_bearer_token),
) -> dict:
    """Return storage backend configuration (no secrets)."""
    settings = get_settings()
    return {
        "backend": settings.storage_backend,
        "bucket": settings.s3_bucket if settings.storage_backend == "s3" else None,
        "endpoint": settings.s3_endpoint_url if settings.storage_backend == "s3" else None,
        "region": settings.s3_region if settings.storage_backend == "s3" else None,
    }
