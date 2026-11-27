from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings

_AI_POST_SUFFIXES = (
    "/extract-knowledge",
    "/generate-notes",
    "/regenerate",
    "/questions/generate",
    "/improvement-plan",
)
_AUTH_PATHS = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
)


class SlidingWindowRateLimiter:
    """Simple thread-safe in-memory per-client sliding-window rate limiter."""

    def __init__(self, window_seconds: int = 60) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(self._window - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = SlidingWindowRateLimiter(window_seconds=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Protect auth and expensive AI generation routes against burst abuse."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        if not settings.effective_rate_limit_enabled or request.method.upper() != "POST":
            return await call_next(request)

        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        bucket_name: str | None = None
        limit = 0

        if path in _AUTH_PATHS:
            bucket_name = f"auth:{client_ip}:{path}"
            limit = settings.rate_limit_auth_per_minute
        elif any(path.endswith(suffix) for suffix in _AI_POST_SUFFIXES):
            bucket_name = f"ai:{client_ip}"
            limit = settings.rate_limit_ai_per_minute

        if bucket_name is not None and limit > 0:
            allowed, retry_after = rate_limiter.allow(bucket_name, limit)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Please wait before retrying.",
                        "code": "RATE_LIMIT_EXCEEDED",
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)
