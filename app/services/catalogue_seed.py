"""Catalogue and connection seeder for IncuBrix Distribution.

Initializes the destination catalogue and connection records for the exactly six
supported connectors:
1. Discourse
2. Lemmy
3. DEV.to
4. Ghost
5. Generic HMAC-signed webhook
6. Assisted publishing

Features:
- Idempotent: Repeat execution never creates duplicate records.
- Credential security: Uses Fernet symmetric encryption via app.services.credentials.
  Never logs or exposes credentials.
- Graceful degradation: If credentials or CREDENTIAL_ENCRYPTION_KEY are missing,
  destinations are still created/updated safely with clear warnings.
- Preserves connector key resolution and links connection records to destinations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.base import new_uuid
from app.db.models.connection import Connection
from app.db.models.destination import Destination
from app.services.credentials import encrypt_credentials, validate_credential_encryption_key

logger = get_logger(__name__)

# The canonical definitions for the six supported connectors
DESTINATION_CATALOGUE_SEEDS: list[dict[str, Any]] = [
    {
        "name": "Random Stuff Discourse",
        "url": "https://random-stuff.discourse.group",
        "platform_key": "discourse",
        "connector_key": "discourse",
        "surface": "topic",
        "category": "4",
        "instance_param": "https://random-stuff.discourse.group",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
    {
        "name": "Lemmy.zip Tech",
        "url": "https://lemmy.zip/c/technology",
        "platform_key": "lemmy",
        "connector_key": "lemmy",
        "surface": "post",
        "category": "technology",
        "instance_param": "https://lemmy.zip",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
    {
        "name": "DEV.to Articles",
        "url": "https://dev.to",
        "platform_key": "devto",
        "connector_key": "devto",
        "surface": "article",
        "category": "programming",
        "instance_param": "https://dev.to/api",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
    {
        "name": "Ghost Blog",
        "url": "https://chmod777life.ghost.io",
        "platform_key": "ghost",
        "connector_key": "ghost",
        "surface": "post",
        "category": "engineering",
        "instance_param": "https://chmod777life.ghost.io",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
    {
        "name": "Webhook.site Integration Endpoint",
        "url": "https://webhook.site/a755d15a-141e-46ee-a789-8ddae3529e60",
        "platform_key": "webhook",
        "connector_key": "webhook_hmac",
        "surface": "webhook",
        "category": "integration",
        "instance_param": "https://webhook.site/a755d15a-141e-46ee-a789-8ddae3529e60",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
    {
        "name": "Assisted Publishing Review",
        "url": "https://example.com/submit",
        "platform_key": "manual",
        "connector_key": "assisted",
        "surface": "pack",
        "category": "editorial",
        "instance_param": "https://example.com/submit",
        "automation_allowed": True,
        "self_promo_allowed": True,
        "link_policy": "allowed",
        "disclosure_required": False,
        "active": True,
    },
]


@dataclass
class SeedResult:
    destinations_created: list[Destination] = field(default_factory=list)
    destinations_updated: list[Destination] = field(default_factory=list)
    connections_created: list[Connection] = field(default_factory=list)
    connections_updated: list[Connection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_destinations(self) -> int:
        return len(self.destinations_created) + len(self.destinations_updated)

    @property
    def total_connections(self) -> int:
        return len(self.connections_created) + len(self.connections_updated)


def _resolve_connector_credentials(
    connector_key: str,
    target_url: str,
    settings: Any,
) -> dict[str, Any] | None:
    """Extract credentials for a connector from settings if configured.

    Returns None if no secret/authentication credential is configured or connector
    does not use authentication (e.g. assisted publishing).
    """
    if connector_key == "discourse":
        if not settings.discourse_api_key:
            return None
        return {
            "api_key": settings.discourse_api_key,
            "api_username": settings.discourse_api_username or "system",
            "base_url": settings.discourse_base_url,
            "category_id": 4,
        }

    if connector_key == "lemmy":
        if not settings.lemmy_password:
            return None
        return {
            "username": settings.lemmy_username,
            "password": settings.lemmy_password,
            "base_url": settings.lemmy_base_url,
            "community_id": settings.lemmy_community_id,
        }

    if connector_key == "devto":
        if not settings.devto_api_key:
            return None
        return {
            "api_key": settings.devto_api_key,
            "base_url": settings.devto_api_base_url,
        }

    if connector_key == "ghost":
        if not settings.ghost_admin_api_key:
            return None
        return {
            "admin_api_key": settings.ghost_admin_api_key,
            "base_url": settings.ghost_api_base_url,
        }

    if connector_key == "webhook_hmac":
        if not settings.hmac_signing_secret:
            return None
        return {
            "hmac_secret": settings.hmac_signing_secret,
            "webhook_url": target_url,
        }

    # assisted connector has auth: none
    return None


async def seed_catalogue_and_connections(session: AsyncSession) -> SeedResult:
    """Idempotently seed the destination catalogue and associated connection records.

    - Upserts the 6 destination records based on (url, platform_key).
    - If CREDENTIAL_ENCRYPTION_KEY is valid and connector credentials exist,
      creates or updates Fernet-encrypted Connection records linked to destinations.
    - If CREDENTIAL_ENCRYPTION_KEY or credentials are unavailable, continues safely.
    """
    settings = get_settings()
    result = SeedResult()

    has_valid_key = validate_credential_encryption_key(settings.credential_encryption_key)
    if not has_valid_key:
        result.warnings.append(
            "CREDENTIAL_ENCRYPTION_KEY is not set or invalid; stored connection credentials will be skipped."
        )

    for seed in DESTINATION_CATALOGUE_SEEDS:
        url = seed["url"]
        platform_key = seed["platform_key"]
        connector_key = seed["connector_key"]

        # ── 1. Find or create Destination ─────────────────────────────────────
        q_dest = select(Destination).where(
            Destination.url == url,
            Destination.platform_key == platform_key,
        )
        dest_res = await session.execute(q_dest)
        destination = dest_res.scalar_one_or_none()

        if destination is None:
            destination = Destination(
                id=new_uuid(),
                name=seed["name"],
                url=url,
                platform_key=platform_key,
                connector_key=connector_key,
                surface=seed.get("surface"),
                category=seed.get("category"),
                instance_param=seed.get("instance_param"),
                automation_allowed=seed.get("automation_allowed", True),
                self_promo_allowed=seed.get("self_promo_allowed", True),
                link_policy=seed.get("link_policy", "allowed"),
                disclosure_required=seed.get("disclosure_required", False),
                active=seed.get("active", True),
            )
            session.add(destination)
            await session.flush()
            result.destinations_created.append(destination)
            logger.info("destination_created", id=destination.id, name=destination.name, connector=connector_key)
        else:
            # Update mutable fields idempotently
            destination.name = seed["name"]
            destination.connector_key = connector_key
            destination.surface = seed.get("surface")
            destination.category = seed.get("category")
            destination.instance_param = seed.get("instance_param")
            destination.automation_allowed = seed.get("automation_allowed", True)
            destination.self_promo_allowed = seed.get("self_promo_allowed", True)
            destination.link_policy = seed.get("link_policy", "allowed")
            destination.disclosure_required = seed.get("disclosure_required", False)
            destination.active = seed.get("active", True)
            await session.flush()
            result.destinations_updated.append(destination)
            logger.info("destination_updated", id=destination.id, name=destination.name, connector=connector_key)

        # ── 2. Handle Connection for connector ────────────────────────────────
        creds = _resolve_connector_credentials(connector_key, url, settings)
        if creds is None:
            # Connector either does not use auth (assisted) or credentials are not yet configured in settings
            continue

        if not has_valid_key:
            # Cannot store encrypted credentials without a valid Fernet key
            continue

        encrypted_blob = encrypt_credentials(creds)
        label = f"{destination.name} Connection"

        # Check existing connection by destination_id
        q_conn = select(Connection).where(Connection.destination_id == destination.id)
        conn_res = await session.execute(q_conn)
        conn = conn_res.scalar_one_or_none()

        if conn is None:
            conn = Connection(
                id=new_uuid(),
                destination_id=destination.id,
                connector_key=connector_key,
                encrypted_credentials=encrypted_blob,
                label=label,
                active=True,
            )
            session.add(conn)
            await session.flush()
            result.connections_created.append(conn)
            logger.info("connection_created", id=conn.id, destination_id=destination.id, connector=connector_key)
        else:
            conn.encrypted_credentials = encrypted_blob
            conn.label = label
            conn.active = True
            await session.flush()
            result.connections_updated.append(conn)
            logger.info("connection_updated", id=conn.id, destination_id=destination.id, connector=connector_key)

    await session.commit()
    return result
