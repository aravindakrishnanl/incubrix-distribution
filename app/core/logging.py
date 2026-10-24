"""Structured JSON logging configuration using structlog.

All log entries include: timestamp, level, logger, event.
Per-request entries add: correlation_id, job_id (when available).
Secrets are redacted before any log emission.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# Patterns for secrets that must never appear in logs.
_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|password|secret|authorization|bearer)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"postgresql\+\w+://[^@]+@"),  # database URL credentials
]


def _redact_secrets(
    logger: Any,
    method_name: str | None = None,
    event_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structlog processor: redact secret values from all string fields.

    Matches structlog processor signature (logger, method_name, event_dict).
    Also supports direct single-argument calls (event_dict).
    """
    if event_dict is None and isinstance(logger, dict):
        event_dict = logger
    elif event_dict is None:
        event_dict = {}

    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            redacted = value
            for pattern in _SECRET_PATTERNS:
                if pattern.groups >= 1:
                    redacted = pattern.sub(r"\1=[REDACTED]", redacted)
                else:
                    redacted = pattern.sub(r"postgresql+asyncpg://[REDACTED]@", redacted)
            event_dict[key] = redacted

        # Also check for obviously secret keys
        if isinstance(key, str) and any(
            s in key.lower() for s in ("password", "secret", "token", "api_key", "auth")
        ):
            if isinstance(value, str) and value:
                event_dict[key] = "[REDACTED]"
    return event_dict



def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output. Call once at startup."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Quiet noisy libraries
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
