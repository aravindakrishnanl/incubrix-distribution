"""Connector contract HTTP routes.

POST /connector/v1/{connector_key}/{method}

All methods follow the Appendix A contract exactly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.connectors.registry import get_connector
from app.core.errors import AppError, UnknownMethodError
from app.core.logging import get_logger
from app.core.security import require_bearer_token

router = APIRouter(prefix="/connector/v1", tags=["connectors"])
logger = get_logger(__name__)

# Methods that do NOT require connection (assisted tier)
_CONNECTIONLESS_METHODS = {"build_assist_pack"}
# Valid method names
_VALID_METHODS = {
    "validate", "publish", "get_status", "delete",
    "fetch_metrics", "refresh_auth", "build_assist_pack",
    "check_connectivity",
}


@router.post("/{connector_key}/{method}")
async def connector_dispatch(
    connector_key: str,
    method: str,
    request: Request,
    _token: str = Depends(require_bearer_token),
) -> Any:
    """Dispatch a method call to the appropriate connector.

    Request body shape depends on the method (see Appendix A).
    All errors are returned as the canonical error envelope.
    """
    if method not in _VALID_METHODS:
        raise UnknownMethodError(connector_key, method)

    connector = get_connector(connector_key)

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    logger.info("connector_dispatch", connector=connector_key, method=method)

    try:
        result = await _invoke(connector, method, body)
    except AppError:
        raise
    except NotImplementedError as exc:
        raise UnknownMethodError(connector_key, method) from exc

    return result


async def _invoke(connector: Any, method: str, body: dict[str, Any]) -> Any:
    if method == "validate":
        return await connector.validate(
            rendition=body.get("rendition", {}),
            destination=body.get("destination", {}),
            connection=body.get("connection", {}),
        )
    elif method == "publish":
        return await connector.publish(
            rendition=body.get("rendition", {}),
            destination=body.get("destination", {}),
            connection=body.get("connection", {}),
            idempotency_key=body.get("idempotency_key", ""),
        )
    elif method == "get_status":
        return await connector.get_status(
            platform_post_id=body.get("platform_post_id", ""),
            connection=body.get("connection", {}),
        )
    elif method == "delete":
        return await connector.delete(
            platform_post_id=body.get("platform_post_id", ""),
            connection=body.get("connection", {}),
        )
    elif method == "fetch_metrics":
        return await connector.fetch_metrics(
            platform_post_id=body.get("platform_post_id", ""),
            connection=body.get("connection", {}),
            since=body.get("since"),
        )
    elif method == "refresh_auth":
        return await connector.refresh_auth(
            connection=body.get("connection", {}),
        )
    elif method == "build_assist_pack":
        return await connector.build_assist_pack(
            rendition=body.get("rendition", {}),
            destination=body.get("destination", {}),
        )
    elif method == "check_connectivity":
        return await connector.check_connectivity(
            connection=body.get("connection", {}),
            destination=body.get("destination", {}),
        )
    else:
        raise NotImplementedError(method)
