"""Destination posting rules and rule evaluation outcomes."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class DestinationRule(Base, TimestampMixin):
    __tablename__ = "destination_rules"
    __table_args__ = (
        UniqueConstraint("destination_id", "rule_type", name="uq_destination_rule"),
        Index("ix_rule_destination_id", "destination_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    destination_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. frequency_cap, self_promo, link_policy, ai_disclosure
    rule_value: Mapped[str | None] = mapped_column(Text)    # JSON
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(200))

    def __repr__(self) -> str:
        return f"<DestinationRule dest={self.destination_id!r} type={self.rule_type!r}>"


class RuleEvaluation(Base, TimestampMixin):
    __tablename__ = "rule_evaluations"
    __table_args__ = (
        Index("ix_rule_eval_job_id", "job_id"),
        Index("ix_rule_eval_destination_id", "destination_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str | None] = mapped_column(String(36))
    destination_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<RuleEvaluation dest={self.destination_id!r} rule={self.rule_type!r} passed={self.passed!r}>"
