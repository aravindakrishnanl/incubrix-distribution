"""IncuBrix Distribution — FastAPI application entry point."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import AsyncGenerator

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, connector, jobs, destinations, storage, connections, certification
from app.connectors.registry import init_registry
from app.core.errors import AppError, app_error_handler, generic_error_handler
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.core.settings import get_settings
from app.db.engine import dispose_engine


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger("startup")
    logger.info("incubrix_distribution_starting", env=settings.app_env, simulation=settings.simulation_mode)

    # Validate security settings (fail-closed in production)
    from app.core.security import validate_security_settings
    validate_security_settings(settings)

    # Initialise connector registry (loads manifests + instances)
    init_registry()
    logger.info("connector_registry_loaded")

    yield

    # Shutdown
    await dispose_engine()
    logger.info("incubrix_distribution_stopped")


settings = get_settings()

app = FastAPI(
    title="IncuBrix Distribution",
    description="Long-Tail Destination Network — connector service and product API",
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(CorrelationIdMiddleware)

# CORS: only enable if explicitly needed (locked down by default)
# app.add_middleware(CORSMiddleware, allow_origins=["https://app.incubrix.io"], ...)

# ── Exception handlers ────────────────────────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)           # /health, /ready
app.include_router(connector.router)        # /connector/v1/{key}/{method}
app.include_router(jobs.router)             # /api/v1/publish, /api/v1/jobs/{id}
app.include_router(destinations.router)     # /api/v1/destinations, /api/v1/connectors
app.include_router(connections.router)      # /api/v1/connections
app.include_router(certification.router)    # /api/v1/certify/{destination_id}
app.include_router(storage.router)          # /api/v1/storage
