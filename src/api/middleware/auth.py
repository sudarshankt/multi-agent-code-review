"""HMAC authentication for webhooks."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class HMACAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/ready"]

    async def dispatch(self, request: Request, call_next):
        # Skip auth for whitelisted paths.
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Only validate webhook endpoints.
        if not request.url.path.endswith("/webhook/github"):
            return await call_next(request)

        settings = get_settings()
        secret = settings.github.webhook_secret
        if not secret:
            logger.warning("webhook_secret_not_configured")
            return JSONResponse(
                {"error": "Webhook secret not configured"},
                status_code=500,
            )

        signature_header = request.headers.get("x-hub-signature-256", "")
        body = await request.body()

        # Recompute HMAC-SHA256.
        computed = "sha256=" + hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(computed, signature_header):
            logger.warning("webhook_auth_failed", remote_addr=request.client.host if request.client else "unknown")
            return JSONResponse(
                {"error": "Invalid signature"},
                status_code=403,
            )

        return await call_next(request)
