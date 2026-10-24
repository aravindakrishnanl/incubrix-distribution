"""Storage abstraction tests.

Tests LocalStorage backend directly.
S3/MinIO tests are marked @pytest.mark.integration and require a running MinIO.
"""

from __future__ import annotations

import pytest
import os
import tempfile

from app.storage.local import LocalStorage
from app.core.settings import get_settings


@pytest.fixture
def local_storage(tmp_path):
    settings = get_settings()
    original = settings.local_storage_path
    settings.local_storage_path = str(tmp_path)
    storage = LocalStorage()
    yield storage
    settings.local_storage_path = original


@pytest.mark.asyncio
async def test_local_put_and_get(local_storage):
    data = b"hello incubrix"
    key = "test/hello.txt"
    returned_key = await local_storage.put(key, data, "text/plain")
    assert returned_key == key
    retrieved = await local_storage.get(key)
    assert retrieved == data


@pytest.mark.asyncio
async def test_local_delete(local_storage):
    key = "test/to_delete.txt"
    await local_storage.put(key, b"delete me")
    await local_storage.delete(key)
    with pytest.raises(Exception):
        await local_storage.get(key)


@pytest.mark.asyncio
async def test_local_health_check(local_storage):
    # Should not raise
    await local_storage.health_check()


@pytest.mark.asyncio
async def test_local_path_traversal_blocked(local_storage):
    with pytest.raises(ValueError, match="Path traversal"):
        await local_storage.put("../../etc/passwd", b"evil")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_s3_put_and_get():
    """Requires a running MinIO at S3_ENDPOINT_URL.

    Run with: pytest -m integration --tb=short
    Requires docker compose up minio minio-init to be running.
    """
    import socket
    settings = get_settings()
    if settings.storage_backend != "s3":
        pytest.skip("S3 backend not configured (STORAGE_BACKEND != s3)")

    # Quick reachability check — skip gracefully if MinIO isn't running
    import urllib.parse
    parsed = urllib.parse.urlparse(settings.s3_endpoint_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9000
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except (OSError, ConnectionRefusedError):
        pytest.skip(f"MinIO not reachable at {settings.s3_endpoint_url} — run: docker compose up minio minio-init")

    from app.storage.s3 import S3Storage
    storage = S3Storage()
    key = "integration-test/hello.txt"
    data = b"integration test data"
    await storage.put(key, data)
    retrieved = await storage.get(key)
    assert retrieved == data
    await storage.delete(key)
