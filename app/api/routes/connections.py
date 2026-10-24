"""Connection management routes — CRUD for connector credentials."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.security import require_bearer_token
from app.db.engine import get_db_session
from app.services.credentials import encrypt_credentials, decrypt_credentials

router = APIRouter(prefix="/api/v1", tags=["connections"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ConnectionCreate(BaseModel):
    connector_key: str
    destination_id: str | None = None
    label: str | None = None
    name: str | None = None
    slug: str | None = None
    base_url: str | None = None
    rate_limit_per_minute: int | None = None
    credentials: dict = {}  # plaintext credentials — will be encrypted at rest


class ConnectionUpdate(BaseModel):
    label: str | None = None
    name: str | None = None
    active: bool | None = None
    rate_limit_per_minute: int | None = None
    credentials: dict | None = None


class ConnectionResponse(BaseModel):
    id: str
    connector_key: str
    destination_id: str | None
    label: str | None
    active: bool
    created_at: str | None
    updated_at: str | None
    # credentials are NEVER returned


def _conn_to_dict(c) -> dict:
    return {
        "id": c.id,
        "slug": c.label or c.id,
        "name": c.label or c.connector_key,
        "connector_key": c.connector_key,
        "destination_id": c.destination_id,
        "label": c.label,
        "active": c.active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/connections")
async def list_connections(
    connector_key: str | None = None,
    destination_id: str | None = None,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List all connections. Credentials are never returned."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    connections = await repo.list_all(connector_key=connector_key, destination_id=destination_id)
    items = [_conn_to_dict(c) for c in connections]
    return {
        "connections": items,
        "items": items,
        "total": len(connections),
    }


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("/connections", status_code=201)
async def create_connection(
    body: ConnectionCreate,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Create a new connection. Credentials are encrypted at rest."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    creds_to_save = dict(body.credentials)
    if body.base_url and "base_url" not in creds_to_save:
        creds_to_save["base_url"] = body.base_url
    if body.rate_limit_per_minute is not None and "rate_limit_per_minute" not in creds_to_save:
        creds_to_save["rate_limit_per_minute"] = body.rate_limit_per_minute

    encrypted = encrypt_credentials(creds_to_save) if creds_to_save else None
    label_to_save = body.slug or body.name or body.label
    conn = await repo.create(
        connector_key=body.connector_key,
        destination_id=body.destination_id,
        label=label_to_save,
        encrypted_credentials=encrypted,
    )
    await db.commit()
    await db.refresh(conn)
    return _conn_to_dict(conn)


# ── Update ─────────────────────────────────────────────────────────────────────

@router.patch("/connections/{connection_id}")
@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: str,
    body: ConnectionUpdate,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Update connection metadata or credentials."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    conn = await repo.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id!r} not found")

    new_label = body.name or body.label
    if new_label is not None:
        conn.label = new_label
    if body.active is not None:
        conn.active = body.active
    if body.credentials is not None:
        conn.encrypted_credentials = encrypt_credentials(body.credentials) if body.credentials else None

    await db.commit()
    await db.refresh(conn)
    return _conn_to_dict(conn)



# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get connection metadata (no credentials)."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    conn = await repo.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id!r} not found")
    return _conn_to_dict(conn)


# ── Decrypt credentials (internal / test helper) ──────────────────────────────

@router.post("/connections/{connection_id}/decrypt")
async def get_connection_credentials(
    connection_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve decrypted credentials for a connection (use with caution)."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    conn = await repo.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id!r} not found")
    if not conn.encrypted_credentials:
        return {"credentials": {}}
    try:
        creds = decrypt_credentials(conn.encrypted_credentials)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt credentials: {exc}")
    return {"credentials": creds}


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/connections/{connection_id}", status_code=200)
async def delete_connection(
    connection_id: str,
    _token: str = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Deactivate a connection (soft delete)."""
    from app.db.repos.connections import ConnectionRepository
    repo = ConnectionRepository(db)
    conn = await repo.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id!r} not found")
    conn.active = False
    await db.commit()
    return {"id": connection_id, "active": False, "message": "Connection deactivated"}
