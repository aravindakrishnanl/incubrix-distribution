"""Destination catalogue model.

Corresponds to Appendix A catalogue fields:
name, url, platform_key, surface, category, audience_tags, language, geo,
est_audience, rules_url, frequency_cap, self_promo_allowed, link_policy,
disclosure_required, automation_allowed, connector_key, relevance_score,
relevance_reason, level, last_certified_at
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Destination(Base, TimestampMixin):
    __tablename__ = "destinations"
    __table_args__ = (
        UniqueConstraint("url", "platform_key", name="uq_destination_url_platform"),
        Index("ix_destination_connector_key", "connector_key"),
        Index("ix_destination_platform_key", "platform_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Core catalogue fields (Appendix A)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    platform_key: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)
    surface: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(200))
    audience_tags: Mapped[str | None] = mapped_column(Text)       # JSON array stored as text
    language: Mapped[str | None] = mapped_column(String(20))
    geo: Mapped[str | None] = mapped_column(String(200))
    est_audience: Mapped[int | None] = mapped_column(Integer)
    rules_url: Mapped[str | None] = mapped_column(String(2048))

    # Posting rules
    frequency_cap: Mapped[str | None] = mapped_column(String(100))  # e.g. "1/week"
    self_promo_allowed: Mapped[bool | None] = mapped_column(Boolean)
    link_policy: Mapped[str | None] = mapped_column(String(200))
    disclosure_required: Mapped[bool | None] = mapped_column(Boolean)
    automation_allowed: Mapped[bool | None] = mapped_column(Boolean)

    # Relevance
    relevance_score: Mapped[int | None] = mapped_column(Integer)    # 1-5
    relevance_reason: Mapped[str | None] = mapped_column(Text)

    # Certification level (L0-L4 per Appendix A)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Instance parameter (e.g. base_url for Discourse)
    instance_param: Mapped[str | None] = mapped_column(String(2048))

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Destination id={self.id!r} name={self.name!r} connector={self.connector_key!r}>"
