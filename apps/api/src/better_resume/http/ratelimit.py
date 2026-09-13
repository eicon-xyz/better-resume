"""Route-class rate limiting middleware: 429 + Retry-After, fail-open on its own bugs.

The bucket is chosen from method + path, the identity from the session cookie (hashed,
never logged raw) with the client address as the fallback for anonymous callers.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..ai_resilience import Bucket, RateLimiter
from ..settings import Settings

logger = structlog.get_logger("better_resume.ratelimit")

#: Always exempt: probes and the generated contract must never be throttled.
WHITELIST = ("/healthz", "/docs", "/redoc", "/openapi.json", "/favicon.ico")

_AI_CALL = (re.compile(r"^/api/v1/chat/sessions/[^/]+/stream$"),)
_ANSWER = (re.compile(r"^/api/v1/interview/sessions/[^/]+/answers$"),)
_HEAVY = (
    re.compile(r"^/api/v1/interview/sessions$"),  # parse resume + generate questions
    re.compile(r"^/api/v1/interview/sessions/[^/]+/questions$"),
    re.compile(r"^/api/v1/interview/sessions/[^/]+/finish$"),  # report generation
)


def classify(method: str, path: str) -> Bucket | None:
    """Return the bucket for this request, or None when it is not rate limited."""
    if path.startswith(WHITELIST):
        return None
    for pattern in _AI_CALL:
        if pattern.match(path):
            return Bucket.AI_CALL
    for pattern in _ANSWER:
        if pattern.match(path):
            return Bucket.ANSWER
    for pattern in _HEAVY:
        if pattern.match(path):
            return Bucket.HEAVY
    if method in ("GET", "HEAD", "OPTIONS"):
        return Bucket.READ
    return Bucket.GENERAL


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        decision = None
        try:
            if limiter is not None and limiter.enabled:
                bucket = classify(request.method, request.url.path)
                if bucket is not None:
                    decision = limiter.check(bucket, _identity(request, self._settings))
        except Exception:  # noqa: BLE001 - limiting is not correctness: fail open
            logger.exception("ratelimit_failed_open", path=request.url.path)
            decision = None

        if decision is not None and not decision.allowed:
            retry_after = max(1, math.ceil(decision.retry_after))
            logger.warning(
                "rate_limited",
                bucket=decision.bucket.value,
                path=request.url.path,
                method=request.method,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"rate limit exceeded for {decision.bucket.value}",
                    "bucket": decision.bucket.value,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Bucket": decision.bucket.value,
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        if decision is not None:
            response.headers["X-RateLimit-Bucket"] = decision.bucket.value
            response.headers["X-RateLimit-Limit"] = str(decision.capacity)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response


def _identity(request: Request, settings: Settings) -> str:
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        return "session:" + hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16]
    client = request.client.host if request.client is not None else "unknown"
    return f"ip:{client}"
