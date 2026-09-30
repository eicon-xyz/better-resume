"""Degradation policy for the shared bucket store (P7 / D19).

When the shared store (Redis) is unavailable the limiter must not turn into a 503, and
must not silently lift every limit either. It falls back to the per-replica bucket — the
semantics shipped before P7 — and stops touching Redis for a cooldown window, so a blink
does not add a socket timeout to every request.

Observability is the point of the policy, not a nicety: every degraded call is counted
(`rate_limit_degraded` in /api/v1/resilience/stats), the transition is logged once, and
the decision carries `scope=instance` so a client can tell the quota is no longer shared.
"""

from __future__ import annotations

import structlog
from redis import exceptions as redis_exceptions

from .clock import Clock
from .metrics import ResilienceMetrics
from .ratelimit import BucketScope, BucketStore

logger = structlog.get_logger("better_resume.ai_resilience.degraded")

#: What "the shared store is unavailable" looks like at this boundary. CancelledError is
#: deliberately not here: a cancelled request is not a degradation.
_UNAVAILABLE = (redis_exceptions.RedisError, OSError, TimeoutError)


class DegradingBucketStore:
    """Primary (shared) store first; on failure serve from the fallback for a cooldown."""

    def __init__(
        self,
        primary: BucketStore,
        fallback: BucketStore,
        *,
        cooldown_seconds: float,
        clock: Clock,
        metrics: ResilienceMetrics,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cooldown = max(0.0, cooldown_seconds)
        self._clock = clock
        self._metrics = metrics
        self._retry_at: float | None = None

    @property
    def scope(self) -> BucketScope:
        return BucketScope.INSTANCE if self._retry_at is not None else BucketScope.SHARED

    @property
    def degraded(self) -> bool:
        return self._retry_at is not None

    @property
    def tracked(self) -> int:
        return self._fallback.tracked

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        if self._retry_at is not None:
            if self._clock.now() < self._retry_at:
                return await self._serve_degraded(key, rate=rate, capacity=capacity)
            return await self._retry_primary(key, rate=rate, capacity=capacity, recovering=True)
        return await self._retry_primary(key, rate=rate, capacity=capacity, recovering=False)

    async def _retry_primary(
        self, key: str, *, rate: float, capacity: float, recovering: bool
    ) -> tuple[bool, float, int]:
        try:
            outcome = await self._primary.take(key, rate=rate, capacity=capacity)
        except _UNAVAILABLE as exc:
            if not recovering:
                logger.warning(
                    "ratelimit_degraded",
                    error=type(exc).__name__,
                    cooldown_seconds=self._cooldown,
                )
            self._retry_at = self._clock.now() + self._cooldown
            return await self._serve_degraded(key, rate=rate, capacity=capacity)
        if recovering:
            logger.info("ratelimit_recovered")
            self._retry_at = None
        return outcome

    async def _serve_degraded(
        self, key: str, *, rate: float, capacity: float
    ) -> tuple[bool, float, int]:
        self._metrics.rate_limit_degraded += 1
        return await self._fallback.take(key, rate=rate, capacity=capacity)

    async def aclose(self) -> None:
        await self._fallback.aclose()
        await self._primary.aclose()
