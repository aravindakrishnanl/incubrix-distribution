"""Destination catalogue routes — full CRUD + bulk import."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.connectors.registry import list_connectors
from app.core.security import require_bearer_token
from app.db.engine import get_db_session
from app.db.repos.destinations import DestinationRepository

router = APIRouter(prefix="/api/v1", tags=["destinations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DestinationCreate(BaseModel):
    name: str
    url: str | None = None
    platform_key: str | None = None
    connector_key: str
    slug: str | None = None
    surface: str | None = None
    category: str | None = None
    audience_tags: list[str] | None = None
    language: str | None = None
    geo: str | None = None
    est_audience: int | None = None
    rules_url: str | None = None
    frequency_cap: str | None = None
    self_promo_allowed: bool | None = None
    link_policy: str | None = None
    disclosure_required: bool | None = None
    automation_allowed: bool | None = None
    relevance_score: int | None = Field(None, ge=1, le=5)
    relevance_reason: str | None = None
    instance_param: str | None = None
    active: bool = True
    rules: list[dict[str, Any]] | None = None
    metadata_: dict[str, Any] | None = None


class DestinationUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    surface: str | None = None
    category: str | None = None
    audience_tags: list[str] | None = None
    language: str | None = None
    geo: str | None = None
    est_audience: int | None = None
    rules_url: str | None = None
    frequency_cap: str | None = None
    self_promo_allowed: bool | None = None
    link_policy: str | None = None
    disclosure_required: bool | None = None
    automation_allowed: bool | None = None
    relevance_score: int | None = Field(None, ge=1, le=5)
    relevance_reason: str | None = None
    instance_param: str | None = None
    active: bool | None = None


def _dest_to_dict(d: Any) -> dict:
    return {
        "id": d.id,
        "slug": d.platform_key,
        "name": d.name,
        "url": d.url,
        "platform_key": d.platform_key,
        "connector_key": d.connector_key,
        "surface": d.surface,
        "category": d.category,
        "audience_tags": json.loads(d.audience_tags) if d.audience_tags else [],
        "language": d.language,
        "geo": d.geo,
        "est_audience": d.est_audience,
        "rules_url": d.rules_url,
        "frequency_cap": d.frequency_cap,
        "self_promo_allowed": d.self_promo_allowed,
        "link_policy": d.link_policy,
        "disclosure_required": d.disclosure_required,
        "automation_allowed": d.automation_allowed,
        "relevance_score": d.relevance_score,
        "relevance_reason": d.relevance_reason,
        "level": d.level,
        "last_certified_at": d.last_certified_at.isoformat() if d.last_certified_at else None,
        "instance_param": d.instance_param,
        "active": d.active,
        "status": "active" if d.active else "inactive",
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/destinations")
async def list_destinations(
    connector_key: str | None = Query(None),
    active: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List all destinations in the catalogue with optional filtering."""
    repo = DestinationRepository(db)
    destinations = await repo.list_all(
        connector_key=connector_key,
        active=active,
        limit=limit,
        offset=offset,
    )
    total = await repo.count(connector_key=connector_key, active=active)
    items = [_dest_to_dict(d) for d in destinations]
    return {
        "destinations": items,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("/destinations", status_code=201)
async def create_destination(
    body: DestinationCreate,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Create a new destination."""
    repo = DestinationRepository(db)
    data = body.model_dump()
    if not data.get("url"):
        data["url"] = f"https://example.com/{data.get('slug', data.get('name', 'dest'))}"
    if not data.get("platform_key"):
        data["platform_key"] = data.get("slug") or data.get("connector_key") or "dest"
    data.pop("slug", None)
    data.pop("rules", None)
    data.pop("metadata_", None)
    # Serialize audience_tags list to JSON string
    if data.get("audience_tags") is not None:
        data["audience_tags"] = json.dumps(data["audience_tags"])
    dest = await repo.create(**data)
    await db.commit()
    await db.refresh(dest)
    return _dest_to_dict(dest)



# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/destinations/{destination_id}")
async def get_destination(
    destination_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get a single destination by ID."""
    repo = DestinationRepository(db)
    dest = await repo.get(destination_id)
    if not dest:
        raise HTTPException(status_code=404, detail=f"Destination {destination_id!r} not found")
    return _dest_to_dict(dest)


# ── Update ─────────────────────────────────────────────────────────────────────

@router.put("/destinations/{destination_id}")
@router.patch("/destinations/{destination_id}")
async def update_destination(
    destination_id: str,
    body: DestinationUpdate,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Update a destination (partial update — only provided fields are changed)."""
    repo = DestinationRepository(db)
    dest = await repo.get(destination_id)
    if not dest:
        raise HTTPException(status_code=404, detail=f"Destination {destination_id!r} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "audience_tags" in updates and updates["audience_tags"] is not None:
        updates["audience_tags"] = json.dumps(updates["audience_tags"])
    dest = await repo.update(destination_id, **updates)
    await db.commit()
    await db.refresh(dest)
    return _dest_to_dict(dest)


# ── Soft-delete (deactivate) ───────────────────────────────────────────────────

@router.delete("/destinations/{destination_id}", status_code=200)
async def delete_destination(
    destination_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Deactivate a destination (soft delete — sets active=False)."""
    repo = DestinationRepository(db)
    dest = await repo.get(destination_id)
    if not dest:
        raise HTTPException(status_code=404, detail=f"Destination {destination_id!r} not found")
    dest = await repo.update(destination_id, active=False)
    await db.commit()
    return {"id": destination_id, "active": False, "status": "inactive", "message": "Destination deactivated"}


from fastapi import Request

@router.post("/destinations/import", status_code=200)
@router.post("/destinations/bulk", status_code=200)
async def bulk_import_destinations(
    request: Request,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Bulk import destinations from JSON body or CSV file upload.

    - JSON body: POST with Content-Type: application/json, body is a list or dict with 'destinations'.
    - CSV file: POST with multipart/form-data, field name 'file', CSV with header row.
    """
    repo = DestinationRepository(db)
    items: list[dict] = []
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if file and hasattr(file, "read"):
            content = await file.read()
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            for row in reader:
                for bool_field in ("self_promo_allowed", "disclosure_required", "automation_allowed", "active"):
                    if bool_field in row and row[bool_field]:
                        row[bool_field] = row[bool_field].lower() in ("true", "1", "yes")
                for int_field in ("est_audience", "relevance_score"):
                    if int_field in row and row[int_field]:
                        try:
                            row[int_field] = int(row[int_field])
                        except ValueError:
                            row[int_field] = None
                if "audience_tags" in row and row["audience_tags"]:
                    try:
                        tags = json.loads(row["audience_tags"])
                        row["audience_tags"] = json.dumps(tags)
                    except json.JSONDecodeError:
                        row["audience_tags"] = json.dumps([t.strip() for t in row["audience_tags"].split(",")])
                items.append(row)
    else:
        try:
            body = await request.json()
        except Exception:
            body = None
        if body:
            raw_list = body.get("destinations", body) if isinstance(body, dict) else body
            if isinstance(raw_list, list):
                for b in raw_list:
                    d = b if isinstance(b, dict) else b.model_dump()
                    if d.get("audience_tags") is not None and isinstance(d["audience_tags"], list):
                        d["audience_tags"] = json.dumps(d["audience_tags"])
                    if not d.get("url"):
                        d["url"] = f"https://example.com/{d.get('slug', d.get('name', 'dest'))}"
                    if not d.get("platform_key"):
                        d["platform_key"] = d.get("slug") or d.get("connector_key") or "dest"
                    valid_keys = {
                        "name", "url", "platform_key", "connector_key", "surface", "category",
                        "audience_tags", "language", "geo", "est_audience", "rules_url",
                        "frequency_cap", "self_promo_allowed", "link_policy", "disclosure_required",
                        "automation_allowed", "relevance_score", "relevance_reason", "level",
                        "instance_param", "active"
                    }
                    filtered = {k: v for k, v in d.items() if k in valid_keys}
                    items.append(filtered)
    if not items:
        raise HTTPException(status_code=400, detail="Provide a JSON body (list) or a CSV file upload.")


    created = []
    errors = []
    for i, item in enumerate(items):
        try:
            for req in ("name", "url", "platform_key", "connector_key"):
                if not item.get(req):
                    raise ValueError(f"Missing required field: {req}")
            dest = await repo.create(**item)
            created.append(dest.id)
        except Exception as exc:
            errors.append({"index": i, "error": str(exc)})

    await db.commit()
    return {
        "created": len(created),
        "imported_count": len(created),
        "error_count": len(errors),
        "ids": created,
        "errors": errors,
    }



# ── Connectors list ────────────────────────────────────────────────────────────

@router.get("/connectors")
async def list_connectors_route(
    _token: str = Depends(require_bearer_token),
) -> dict:
    """List all registered connectors with their status."""
    return {"connectors": list_connectors()}
