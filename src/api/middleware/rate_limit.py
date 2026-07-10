"""Rate limiting middleware: sliding window per client IP."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# In-memory sliding window: client_ip -> list[timestamp]
_window: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window_seconds

        # Trim old requests outside the window.
        _window[client_ip] = [ts for ts in _window[client_ip] if ts > cutoff]

        # Check if over limit.
        if len(_window[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                {"error": "Rate limit exceeded"},
                status_code=429,
            )

        # Record this request.
        _window[client_ip].append(now)
        return await call_next(request)
