"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.review import HealthResponse, ReadyResponse
from src.core.config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Simple liveness check."""
    return HealthResponse(status="healthy")


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness check: confirms config is loaded."""
    settings = get_settings()
    return ReadyResponse(
        status="ready",
        environment=settings.app.env,
        version=settings.app.version,
    )
