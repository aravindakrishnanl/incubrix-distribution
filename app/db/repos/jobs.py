"""Job repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_uuid
from app.db.models.job import JobState, PublishJob


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        connector_key: str | None = None,
        destination_id: str | None = None,
        idempotency_key: str | None = None,
        callback_url: str | None = None,
    ) -> PublishJob:
        job = PublishJob(
            id=new_uuid(),
            state=JobState.QUEUED,
            progress=0,
            connector_key=connector_key,
            destination_id=destination_id,
            idempotency_key=idempotency_key,
            callback_url=callback_url,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get(self, job_id: str) -> PublishJob | None:
        result = await self._session.execute(
            select(PublishJob).where(PublishJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_state(
        self,
        job_id: str,
        state: JobState,
        progress: int = 0,
        platform_post_id: str | None = None,
        live_url: str | None = None,
        result_url: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        job = await self.get(job_id)
        if not job:
            return
        job.state = state
        job.progress = progress
        if platform_post_id is not None:
            job.platform_post_id = platform_post_id
        if live_url is not None:
            job.live_url = live_url
        if result_url is not None:
            job.result_url = result_url
        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message
        await self._session.flush()
