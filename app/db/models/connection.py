"""Connection model — references to connector credential configuration.

Credentials are NEVER stored in plaintext. The encrypted_credentials field
stores the credential JSON encrypted with the configured CREDENTIAL_ENCRYPTION_KEY
using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

Key management: the encryption key is injected via environment variable.
Key rotation: re-encrypt all records with the new key, then update the variable.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"
    __table_args__ = (
        Index("ix_connection_connector_key", "connector_key"),
        Index("ix_connection_destination_id", "destination_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    destination_id: Mapped[str | None] = mapped_column(String(36))
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Encrypted blob — use app.services.credentials to read/write
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)

    # Non-secret connection metadata
    label: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Connection id={self.id!r} connector={self.connector_key!r}>"
