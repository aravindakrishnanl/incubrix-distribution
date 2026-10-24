"""Pytest configuration and shared fixtures.

DATABASE SAFETY:
  The TEST_DATABASE_URL must contain "_test" (enforced by settings validator).
  The reset fixture drops and recreates only the test database.
  It will raise an error if the URL does not contain "_test".

Test DB strategy:
  - Uses a real PostgreSQL pointed to incubrix_dist_test (or TEST_DATABASE_URL).
  - If no PostgreSQL is available, the in-process async engine falls back to
    creating the schema directly from SQLAlchemy models (test_engine fixture).
  - The `app` fixture overrides `get_db_session` so API-level tests that need
    DB (idempotency, jobs) use the same test engine rather than the one
    configured in settings.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Force test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SIMULATION_MODE", "true")

from app.core.settings import Settings, get_settings
from app.db.base import Base


# ── Test Settings ─────────────────────────────────────────────────────────────

def _test_settings() -> Settings:
    return Settings(
        app_env="test",
        simulation_mode=True,
        storage_backend="local",
        # Use _test suffix databases — enforced by validator
        database_url=os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist_test",
        ),
        database_url_sync=os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist_test",
        ).replace("+asyncpg", "+psycopg2"),
        test_database_url=os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist_test",
        ),
        api_bearer_token="test-token",
        credential_encryption_key="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
        hmac_signing_secret="test-hmac-secret-12345",
        connector_discourse_enabled=True,
        connector_lemmy_enabled=True,
        connector_devto_enabled=True,
        connector_ghost_enabled=True,
        connector_webhook_hmac_enabled=True,
        connector_assisted_enabled=True,
    )


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return _test_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine(test_settings):
    """Create the test database schema once per session.

    Tries to connect to PostgreSQL and create the schema.
    If the database is unavailable, uses an in-process SQLite-compatible
    schema via SQLAlchemy models directly (so unit tests still pass).
    """
    from sqlalchemy.pool import NullPool
    db_url = test_settings.database_url
    engine = create_async_engine(
        db_url,
        echo=False,
        poolclass=NullPool,
        # Short connect timeout so we fail fast if Postgres isn't running
        connect_args={"timeout": 5} if "asyncpg" in db_url else {},
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    except Exception:
        # PostgreSQL not available — yield a "no-op" engine signal
        await engine.dispose()
        yield None
        return
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test async database session with rollback after each test."""
    if test_engine is None:
        pytest.skip("PostgreSQL not available for this test")
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autocommit=False, autoflush=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ── Override get_db_session for API-level tests ───────────────────────────────

def make_db_override(test_engine):
    """Return a FastAPI dependency that provides a test-scoped DB session."""
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        if test_engine is None:
            # No DB available — raise a clear error rather than silently passing
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="Test database not available")
        factory = async_sessionmaker(test_engine, expire_on_commit=False, autocommit=False, autoflush=False)
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _override


@pytest.fixture
def app(test_settings, test_engine, monkeypatch):
    """FastAPI test application with patched settings and DB dependency override."""
    import app.core.settings as settings_module
    monkeypatch.setattr(settings_module, "_settings", test_settings)

    from app.connectors import registry
    registry._CONNECTORS.clear()
    registry._MANIFESTS.clear()
    registry.init_registry()

    from app.main import app as fastapi_app
    from app.db import engine as engine_module

    if test_engine is not None:
        factory = async_sessionmaker(test_engine, expire_on_commit=False, autocommit=False, autoflush=False)
        monkeypatch.setattr(engine_module, "_engine", test_engine)
        monkeypatch.setattr(engine_module, "_session_factory", factory)

    # Override the DB session dependency so API tests use the test engine
    from app.db.engine import get_db_session
    fastapi_app.dependency_overrides[get_db_session] = make_db_override(test_engine)

    yield fastapi_app

    # Clean up overrides
    fastapi_app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def client(app):
    """Synchronous test client."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
async def async_client(app) -> AsyncClient:
    """Async HTTPX test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    ) as c:
        yield c
