"""Request middleware: correlation ID injection and structured logging."""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inject X-Correlation-Id into request context and response headers.

    If the caller supplies X-Correlation-Id, that value is used; otherwise
    a new UUID4 is generated. The ID is stored in structlog context variables
    so every log line emitted during the request includes it automatically.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - start
            logger.exception("Unhandled exception", elapsed_ms=round(elapsed * 1000, 1))
            raise

        elapsed = time.perf_counter() - start
        logger.info(
            "request_complete",
            status_code=response.status_code,
            elapsed_ms=round(elapsed * 1000, 1),
        )

        response.headers["X-Correlation-Id"] = correlation_id
        return response
