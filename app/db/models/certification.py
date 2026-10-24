"""Certification run model — stores evidence of each certification attempt."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class CertificationRun(Base, TimestampMixin):
    __tablename__ = "certification_runs"
    __table_args__ = (
        Index("ix_cert_destination_id", "destination_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    destination_id: Mapped[str] = mapped_column(String(36), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Run outcome
    passed: Mapped[bool | None] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Evidence references (S3 keys or URLs)
    publish_response: Mapped[str | None] = mapped_column(Text)   # JSON
    live_url: Mapped[str | None] = mapped_column(String(2048))
    status_response: Mapped[str | None] = mapped_column(Text)    # JSON
    delete_response: Mapped[str | None] = mapped_column(Text)    # JSON
    screenshot_s3_key: Mapped[str | None] = mapped_column(String(1000))

    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<CertificationRun id={self.id!r} passed={self.passed!r}>"
