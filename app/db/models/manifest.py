"""Output manifest model — records what was used to produce each artifact."""

from __future__ import annotations

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class OutputManifest(Base, TimestampMixin):
    __tablename__ = "output_manifests"
    __table_args__ = (
        Index("ix_manifest_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # JSON blobs matching IS-9 output manifest spec
    manifest_json: Mapped[str | None] = mapped_column(Text)    # full manifest
    s3_key: Mapped[str | None] = mapped_column(String(1000))   # if stored to S3

    def __repr__(self) -> str:
        return f"<OutputManifest job={self.job_id!r}>"
