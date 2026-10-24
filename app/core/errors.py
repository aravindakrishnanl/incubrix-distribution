"""Canonical error codes, error envelope, and exception hierarchy.

All error codes are UPPER_SNAKE_CASE as specified in Appendix A.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCode(StrEnum):
    # ── Connector / destination errors (Appendix A) ──────────────────────────
    DEST_SPEC_VIOLATION = "DEST_SPEC_VIOLATION"
    DEST_RULE_FREQUENCY_CAP = "DEST_RULE_FREQUENCY_CAP"
    CONNECTION_AUTH_EXPIRED = "CONNECTION_AUTH_EXPIRED"
    PLATFORM_RATE_LIMIT = "PLATFORM_RATE_LIMIT"
    PLATFORM_QUOTA_EXHAUSTED = "PLATFORM_QUOTA_EXHAUSTED"
    PLATFORM_CONTENT_REJECTED = "PLATFORM_CONTENT_REJECTED"
    PLATFORM_UNAVAILABLE = "PLATFORM_UNAVAILABLE"
    CONNECTOR_DISABLED = "CONNECTOR_DISABLED"

    # ── Application-level errors ──────────────────────────────────────────────
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_CONNECTOR = "UNKNOWN_CONNECTOR"
    UNKNOWN_METHOD = "UNKNOWN_METHOD"


# Retryability per error code (from Appendix A).
_RETRYABLE: dict[ErrorCode, bool | str] = {
    ErrorCode.DEST_SPEC_VIOLATION: False,
    ErrorCode.DEST_RULE_FREQUENCY_CAP: "Later",
    ErrorCode.CONNECTION_AUTH_EXPIRED: "After reconnect",
    ErrorCode.PLATFORM_RATE_LIMIT: True,
    ErrorCode.PLATFORM_QUOTA_EXHAUSTED: "Next window",
    ErrorCode.PLATFORM_CONTENT_REJECTED: False,
    ErrorCode.PLATFORM_UNAVAILABLE: True,
    ErrorCode.CONNECTOR_DISABLED: False,
}

# HTTP status codes per error code.
_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.DEST_SPEC_VIOLATION: 422,
    ErrorCode.DEST_RULE_FREQUENCY_CAP: 429,
    ErrorCode.CONNECTION_AUTH_EXPIRED: 401,
    ErrorCode.PLATFORM_RATE_LIMIT: 429,
    ErrorCode.PLATFORM_QUOTA_EXHAUSTED: 429,
    ErrorCode.PLATFORM_CONTENT_REJECTED: 422,
    ErrorCode.PLATFORM_UNAVAILABLE: 503,
    ErrorCode.CONNECTOR_DISABLED: 503,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.UNKNOWN_CONNECTOR: 404,
    ErrorCode.UNKNOWN_METHOD: 404,
}


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool | str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AppError(Exception):
    """Base application exception. Always translates to a structured JSON error response."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status or _HTTP_STATUS.get(code, 500)
        self.retryable = _RETRYABLE.get(code, False)
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.http_status,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code=self.code,
                    message=self.message,
                    retryable=self.retryable,
                    details=self.details,
                )
            ).model_dump(),
        )


# ── Specific exception classes ─────────────────────────────────────────────────
class ConnectorDisabledError(AppError):
    def __init__(self, connector_key: str) -> None:
        super().__init__(
            ErrorCode.CONNECTOR_DISABLED,
            f"Connector '{connector_key}' is disabled.",
        )


class UnknownConnectorError(AppError):
    def __init__(self, connector_key: str) -> None:
        super().__init__(
            ErrorCode.UNKNOWN_CONNECTOR,
            f"No connector found with key '{connector_key}'.",
        )


class UnknownMethodError(AppError):
    def __init__(self, connector_key: str, method: str) -> None:
        super().__init__(
            ErrorCode.UNKNOWN_METHOD,
            f"Connector '{connector_key}' has no method '{method}'.",
        )


class IdempotencyConflictError(AppError):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            ErrorCode.IDEMPOTENCY_CONFLICT,
            f"Idempotency key '{idempotency_key}' was already used with a different request payload.",
            details={"idempotency_key": idempotency_key},
        )


class DestSpecViolationError(AppError):
    def __init__(self, violations: list[dict[str, Any]]) -> None:
        super().__init__(
            ErrorCode.DEST_SPEC_VIOLATION,
            "Content violates destination specification.",
            details={"violations": violations},
        )


class PlatformRateLimitError(AppError):
    def __init__(self, retry_after: int | None = None) -> None:
        details = {"retry_after_seconds": retry_after} if retry_after else {}
        super().__init__(
            ErrorCode.PLATFORM_RATE_LIMIT,
            "Platform rate limit reached.",
            details=details,
        )


class PlatformUnavailableError(AppError):
    def __init__(self, platform: str) -> None:
        super().__init__(
            ErrorCode.PLATFORM_UNAVAILABLE,
            f"Platform '{platform}' is currently unavailable.",
        )


class AuthExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONNECTION_AUTH_EXPIRED,
            "Platform credentials have expired or been revoked.",
        )


# ── FastAPI exception handlers ─────────────────────────────────────────────────

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError into the standard error envelope."""
    return exc.to_response()


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: never leak stack traces or secrets to clients."""
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR,
                message="An internal error occurred.",
                retryable=False,
                details={},
            )
        ).model_dump(),
    )
