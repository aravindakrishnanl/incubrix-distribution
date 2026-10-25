"""Tests for destination catalogue and connection initialization (seeding).

Verifies:
1. Seed creates exactly six destinations (one for each required connector).
2. Repeat execution is idempotent (updates existing records, creates zero duplicates).
3. Stored credentials are Fernet-encrypted (never plaintext or legacy base64).
4. Missing CREDENTIAL_ENCRYPTION_KEY degrades safely without crashing destination seeding.
5. Missing individual connector credentials skips connection creation safely.
6. Unified CLI commands ('seed' and 'destinations') work correctly.
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.cli.main import async_cli_entrypoint, run_list_destinations
from app.core.settings import get_settings
from app.db.models.connection import Connection
from app.db.models.destination import Destination
from app.services.catalogue_seed import (
    DESTINATION_CATALOGUE_SEEDS,
    seed_catalogue_and_connections,
)
from app.services.credentials import decrypt_credentials


@pytest.fixture
def session_factory(test_engine):
    """Session factory for clean per-operation async sessions."""
    if test_engine is None:
        pytest.skip("Test database not available")
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def clean_db_tables(session_factory):
    """Ensure destinations and connections tables are clean before each test."""
    async with session_factory() as session:
        await session.execute(delete(Connection))
        await session.execute(delete(Destination))
        await session.commit()
    yield
    async with session_factory() as session:
        await session.execute(delete(Connection))
        await session.execute(delete(Destination))
        await session.commit()


@pytest.mark.asyncio
async def test_seed_creates_exactly_six_destinations(session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "discourse_api_key", "test_disc_key")
    monkeypatch.setattr(settings, "discourse_api_username", "test_user")
    monkeypatch.setattr(settings, "lemmy_password", "test_lemmy_pass")
    monkeypatch.setattr(settings, "devto_api_key", "test_devto_key")
    monkeypatch.setattr(settings, "ghost_admin_api_key", "kid:0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "hmac_signing_secret", "test_hmac_secret")

    async with session_factory() as session:
        result = await seed_catalogue_and_connections(session)

        # 1. Assert exactly 6 destinations created
        assert len(result.destinations_created) == 6
        assert len(result.destinations_updated) == 0

        expected_connectors = {"discourse", "lemmy", "devto", "ghost", "webhook_hmac", "assisted"}
        created_connectors = {d.connector_key for d in result.destinations_created}
        assert created_connectors == expected_connectors

        # 2. Assert exactly 5 connections created (assisted has no authentication)
        assert len(result.connections_created) == 5
        assert len(result.connections_updated) == 0

        conn_connectors = {c.connector_key for c in result.connections_created}
        assert conn_connectors == {"discourse", "lemmy", "devto", "ghost", "webhook_hmac"}

        # 3. Assert all connections are properly linked to destination IDs
        dest_ids = {d.id for d in result.destinations_created}
        for c in result.connections_created:
            assert c.destination_id in dest_ids
            assert c.active is True


@pytest.mark.asyncio
async def test_seed_repeat_execution_is_idempotent(session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "discourse_api_key", "test_disc_key")
    monkeypatch.setattr(settings, "lemmy_password", "test_lemmy_pass")
    monkeypatch.setattr(settings, "devto_api_key", "test_devto_key")
    monkeypatch.setattr(settings, "ghost_admin_api_key", "kid:0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "hmac_signing_secret", "test_hmac_secret")

    # Run 1: initial seed
    async with session_factory() as session1:
        res1 = await seed_catalogue_and_connections(session1)
        assert len(res1.destinations_created) == 6
        assert len(res1.connections_created) == 5

    # Run 2: repeat execution on same database state in fresh session
    async with session_factory() as session2:
        res2 = await seed_catalogue_and_connections(session2)
        assert len(res2.destinations_created) == 0
        assert len(res2.destinations_updated) == 6
        assert len(res2.connections_created) == 0
        assert len(res2.connections_updated) == 5

        # Total counts in DB must strictly remain 6 and 5 (no duplicates)
        dest_count = (await session2.execute(select(func.count()).select_from(Destination))).scalar_one()
        conn_count = (await session2.execute(select(func.count()).select_from(Connection))).scalar_one()
        assert dest_count == 6
        assert conn_count == 5


@pytest.mark.asyncio
async def test_seed_credentials_are_fernet_encrypted(session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "devto_api_key", "super_secret_devto_token")
    monkeypatch.setattr(settings, "discourse_api_key", "super_secret_discourse_key")

    async with session_factory() as session:
        await seed_catalogue_and_connections(session)

        # Inspect connection records
        res = await session.execute(select(Connection).where(Connection.connector_key == "devto"))
        conn = res.scalar_one()

        # Must be encrypted with Fernet (starts with gAAAAA)
        assert conn.encrypted_credentials.startswith("gAAAAA")
        assert "super_secret" not in conn.encrypted_credentials
        assert not conn.encrypted_credentials.startswith("b64:")

        # Must successfully decrypt to original dictionary
        decrypted = decrypt_credentials(conn.encrypted_credentials)
        assert decrypted["api_key"] == "super_secret_devto_token"


@pytest.mark.asyncio
async def test_seed_with_missing_encryption_key_continues_safely(session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "credential_encryption_key", "")
    monkeypatch.setattr(settings, "devto_api_key", "my_key")

    async with session_factory() as session:
        result = await seed_catalogue_and_connections(session)

        # 6 destinations must still be created
        assert len(result.destinations_created) == 6
        # 0 connections created because encryption key was unavailable
        assert len(result.connections_created) == 0
        # Must report a warning
        assert any("CREDENTIAL_ENCRYPTION_KEY" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_seed_with_missing_connector_credentials(session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "discourse_api_key", "")
    monkeypatch.setattr(settings, "lemmy_password", "")
    monkeypatch.setattr(settings, "devto_api_key", "")
    monkeypatch.setattr(settings, "ghost_admin_api_key", "")
    monkeypatch.setattr(settings, "hmac_signing_secret", "")

    async with session_factory() as session:
        result = await seed_catalogue_and_connections(session)

        # All 6 destinations are created
        assert len(result.destinations_created) == 6
        # No connections created for connectors without credentials
        assert len(result.connections_created) == 0


@pytest.mark.asyncio
async def test_cli_seed_subcommand():
    with patch("app.cli.main.run_seed_command", new=AsyncMock(return_value=0)) as mock_seed:
        code = await async_cli_entrypoint(["seed"])
        assert code == 0
        mock_seed.assert_called_once()


@pytest.mark.asyncio
async def test_cli_destinations_offline_direct_db_fallback(monkeypatch):
    # Simulate API server being offline (ConnectError)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aexit__ = AsyncMock(return_value=None)

    fake_dest = SimpleNamespace(
        id="d-123",
        name="Discourse Forum",
        connector_key="discourse",
        platform_key="discourse",
        url="https://forum.example.com",
        category="community",
        rules_url=None,
        frequency_cap=None,
        self_promo_allowed=True,
        link_policy="allowed",
        disclosure_required=False,
        automation_allowed=True,
        instance_param="https://forum.example.com",
        active=True,
    )

    mock_session = AsyncMock()
    mock_session.list_all = AsyncMock(return_value=[fake_dest])

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("app.db.engine.get_session_factory", return_value=mock_factory), \
         patch("app.db.repos.destinations.DestinationRepository.list_all", new=AsyncMock(return_value=[fake_dest])):

        args = argparse.Namespace(token="test-token", base_url="http://localhost:8000")
        code = await run_list_destinations(args)
        assert code == 0
