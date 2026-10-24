
"""Connector registry — loads all connectors and their manifests.

A connector is identified by its key (e.g. "discourse").
The registry is a singleton populated at application startup.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.errors import ConnectorDisabledError, UnknownConnectorError
from app.core.settings import get_settings

if TYPE_CHECKING:
    from app.connectors.base import BaseConnector

_MANIFEST_DIR = Path(__file__).parent / "manifests"
_CONNECTORS: dict[str, "BaseConnector"] = {}
_MANIFESTS: dict[str, dict] = {}


def _load_manifests() -> None:
    for path in _MANIFEST_DIR.glob("*.yaml"):
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            _MANIFESTS[data["key"]] = data


def _register_connectors() -> None:
    from app.connectors.implementations.discourse import DiscourseConnector
    from app.connectors.implementations.lemmy import LemmyConnector
    from app.connectors.implementations.devto import DevToConnector
    from app.connectors.implementations.ghost import GhostConnector
    from app.connectors.implementations.webhook_hmac import WebhookHmacConnector
    from app.connectors.implementations.assisted import AssistedConnector

    for cls in [
        DiscourseConnector,
        LemmyConnector,
        DevToConnector,
        GhostConnector,
        WebhookHmacConnector,
        AssistedConnector,
    ]:
        instance = cls()
        _CONNECTORS[instance.key] = instance


def init_registry() -> None:
    """Initialise the connector registry. Call once at startup."""
    _load_manifests()
    _register_connectors()


def get_connector(key: str) -> "BaseConnector":
    """Return a connector by key, enforcing the enabled toggle."""
    settings = get_settings()
    if key not in _CONNECTORS:
        raise UnknownConnectorError(key)
    if not settings.connector_enabled(key):
        raise ConnectorDisabledError(key)
    return _CONNECTORS[key]


def get_manifest(key: str) -> dict:
    """Return the YAML manifest dict for a connector key."""
    if key not in _MANIFESTS:
        raise UnknownConnectorError(key)
    return _MANIFESTS[key]


def list_connectors() -> list[dict]:
    """Return all registered connectors with enabled status."""
    settings = get_settings()
    result = []
    for key, connector in _CONNECTORS.items():
        result.append({
            "key": key,
            "version": getattr(connector, "version", "unknown"),
            "tier": getattr(connector, "tier", "unknown"),
            "enabled": settings.connector_enabled(key),
        })
    return result
