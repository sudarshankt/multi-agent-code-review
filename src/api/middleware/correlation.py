"""Correlation ID middleware: extracts/generates X-Correlation-ID headers."""

from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.core.logging import set_correlation_id


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response
