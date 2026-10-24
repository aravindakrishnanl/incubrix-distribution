"""Local filesystem storage backend (developer convenience only).

WARNING: This does NOT satisfy the S3-compatible storage requirement.
Use only for fast local development iteration. Full-stack tests must use S3Storage.
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.storage.base import BaseStorage

logger = get_logger(__name__)


class LocalStorage(BaseStorage):
    def __init__(self) -> None:
        settings = get_settings()
        self._root = Path(settings.local_storage_path)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if not str(p).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal attempt: {key!r}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._path(key).write_bytes(data)
        logger.info("local_storage_put", key=key)
        return key

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        # No real presigned URLs for local storage — return a placeholder
        return f"/api/v1/storage/download?key={key}"

    async def health_check(self) -> None:
        test_file = self._root / ".health"
        test_file.write_bytes(b"ok")
        test_file.unlink()
