"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.endpoints import health, review, sse, webhook
from src.api.endpoints import fixes
from src.api.middleware import CorrelationIDMiddleware, HMACAuthMiddleware, RateLimitMiddleware
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context: startup and shutdown hooks."""
    settings = get_settings()
    configure_logging(level=settings.app.log_level, json_logs=settings.app.log_json)
    logger.info(
        "app_starting",
        version=settings.app.version,
        env=settings.app.env,
        api_port=settings.api.port,
    )
    yield
    logger.info("app_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Cap PR Review",
        version=settings.app.version,
        description="AI-powered multi-agent PR review system",
        lifespan=lifespan,
    )

    # ---- CORS ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Custom middleware (order matters: rightmost runs first) ----
    # 1. Rate limit
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.api.rate_limit_per_minute)
    # 2. Correlation ID
    app.add_middleware(CorrelationIDMiddleware)
    # 3. HMAC auth (for webhooks)
    app.add_middleware(
        HMACAuthMiddleware,
        exclude_paths=["/health", "/ready", f"{settings.api.prefix}/reviews"],
    )

    # ---- Routers ----
    app.include_router(health.router, tags=["health"])
    app.include_router(
        review.router,
        prefix=settings.api.prefix,
        tags=["reviews"],
    )
    app.include_router(
        sse.router,
        prefix=f"{settings.api.prefix}/sse",
        tags=["sse"],
    )
    app.include_router(
        webhook.router,
        prefix=f"{settings.api.prefix}/webhook",
        tags=["webhooks"],
    )
    app.include_router(
        fixes.router,
        prefix=settings.api.prefix,
        tags=["fixes"],
    )

    return app


# ASGI app entry point.
app = create_app()
