"""Publish job model and state machine."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PublishJob(Base, TimestampMixin):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        Index("ix_job_state", "state"),
        Index("ix_job_idempotency_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    idempotency_key: Mapped[str | None] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(50), default=JobState.QUEUED, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100

    # Context
    destination_id: Mapped[str | None] = mapped_column(String(36))
    connector_key: Mapped[str | None] = mapped_column(String(100))

    # Result links (populated when succeeded)
    result_url: Mapped[str | None] = mapped_column(String(2048))
    platform_post_id: Mapped[str | None] = mapped_column(String(500))
    live_url: Mapped[str | None] = mapped_column(String(2048))

    # Error (populated when failed)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Callback URL (optional, signed with HMAC-SHA256)
    callback_url: Mapped[str | None] = mapped_column(String(2048))

    def __repr__(self) -> str:
        return f"<PublishJob id={self.id!r} state={self.state!r}>"
