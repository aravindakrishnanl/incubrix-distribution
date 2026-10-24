"""Idempotency record — prevents duplicate operations.

The fingerprint is a SHA-256 hash of (idempotency_key + request_body_hash).
The uniqueness constraint on (idempotency_key, fingerprint) ensures that:
  - Same key + same payload: returns stored result (no side effect repeated).
  - Same key + different payload: raises IDEMPOTENCY_CONFLICT.

These records persist across process restarts.
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class IdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
        Index("ix_idempotency_key", "idempotency_key"),
        Index("ix_idempotency_fingerprint", "fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    idempotency_key: Mapped[str] = mapped_column(String(500), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex
    job_id: Mapped[str | None] = mapped_column(String(36))
    # Stored result for fast replay without job lookup
    stored_result: Mapped[str | None] = mapped_column(Text)  # JSON

    def __repr__(self) -> str:
        return f"<IdempotencyRecord key={self.idempotency_key!r} job={self.job_id!r}>"
