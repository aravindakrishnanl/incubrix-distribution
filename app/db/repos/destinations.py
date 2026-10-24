"""Destination repository."""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.destination import Destination


class DestinationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(
        self,
        connector_key: str | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Destination]:
        q = select(Destination)
        if connector_key is not None:
            q = q.where(Destination.connector_key == connector_key)
        if active is not None:
            q = q.where(Destination.active == active)
        q = q.order_by(Destination.name).limit(limit).offset(offset)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def count(
        self,
        connector_key: str | None = None,
        active: bool | None = None,
    ) -> int:
        q = select(func.count()).select_from(Destination)
        if connector_key is not None:
            q = q.where(Destination.connector_key == connector_key)
        if active is not None:
            q = q.where(Destination.active == active)
        result = await self._session.execute(q)
        return result.scalar_one()

    async def get(self, destination_id: str) -> Destination | None:
        result = await self._session.execute(
            select(Destination).where(Destination.id == destination_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Destination:
        from app.db.base import new_uuid
        kwargs.setdefault("active", True)
        kwargs.setdefault("level", 0)
        dest = Destination(id=new_uuid(), **kwargs)
        self._session.add(dest)
        await self._session.flush()
        return dest

    async def update(self, destination_id: str, **kwargs) -> Destination:
        dest = await self.get(destination_id)
        if not dest:
            raise ValueError(f"Destination {destination_id!r} not found")
        for key, value in kwargs.items():
            if hasattr(dest, key):
                setattr(dest, key, value)
        await self._session.flush()
        return dest
