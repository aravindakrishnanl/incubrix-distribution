"""Storage abstraction interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStorage(ABC):
    """Abstract storage backend. Implementations: S3Storage, LocalStorage."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload data and return the S3 key."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Download data by key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object by key."""

    @abstractmethod
    async def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned download URL."""

    @abstractmethod
    async def health_check(self) -> None:
        """Raise an exception if the storage backend is not reachable."""
