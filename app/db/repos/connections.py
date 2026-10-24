"""Connection repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.connection import Connection


class ConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(
        self,
        connector_key: str | None = None,
        destination_id: str | None = None,
    ) -> list[Connection]:
        q = select(Connection)
        if connector_key is not None:
            q = q.where(Connection.connector_key == connector_key)
        if destination_id is not None:
            q = q.where(Connection.destination_id == destination_id)
        q = q.order_by(Connection.created_at.desc())
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get(self, connection_id: str) -> Connection | None:
        result = await self._session.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Connection:
        from app.db.base import new_uuid
        kwargs.setdefault("active", True)
        conn = Connection(id=new_uuid(), **kwargs)
        self._session.add(conn)
        await self._session.flush()
        return conn
