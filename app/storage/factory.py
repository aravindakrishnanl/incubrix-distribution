"""Storage factory — returns the configured storage backend."""

from __future__ import annotations

from app.core.settings import get_settings
from app.storage.base import BaseStorage

_storage: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_backend == "s3":
            from app.storage.s3 import S3Storage
            _storage = S3Storage()
        else:
            from app.storage.local import LocalStorage
            _storage = LocalStorage()
    return _storage
