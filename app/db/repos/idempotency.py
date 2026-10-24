"""Idempotency record repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_uuid
from app.db.models.idempotency import IdempotencyRecord


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, idempotency_key: str) -> IdempotencyRecord | None:
        result = await self._session.execute(
            select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        idempotency_key: str,
        fingerprint: str,
        job_id: str | None = None,
        stored_result: str | None = None,
    ) -> IdempotencyRecord:
        record = IdempotencyRecord(
            id=new_uuid(),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            job_id=job_id,
            stored_result=stored_result,
        )
        self._session.add(record)
        await self._session.flush()
        return record
