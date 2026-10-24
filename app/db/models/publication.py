"""Publication record — tracks each external post."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Publication(Base, TimestampMixin):
    __tablename__ = "publications"
    __table_args__ = (
        Index("ix_publication_job_id", "job_id"),
        Index("ix_publication_destination_id", "destination_id"),
        Index("ix_publication_platform_post_id", "platform_post_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    destination_id: Mapped[str | None] = mapped_column(String(36))
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # External reference
    platform_post_id: Mapped[str | None] = mapped_column(String(500))
    live_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str | None] = mapped_column(String(100))

    # Deletion tracking
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Publication id={self.id!r} platform_post_id={self.platform_post_id!r}>"
