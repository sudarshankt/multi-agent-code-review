"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException

from src.core.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Gate write/expensive endpoints behind a shared-secret header.

    No-op when `API_KEY` isn't configured (local dev default). Set it for
    any public deployment — callers must then send a matching `X-API-Key`
    header on create-review, apply-fixes, and test-run requests.
    """
    configured_key = get_settings().api_key
    if not configured_key:
        return
    if x_api_key != configured_key:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
