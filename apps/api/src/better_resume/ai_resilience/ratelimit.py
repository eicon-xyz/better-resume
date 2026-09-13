"""In-process token buckets per route class and identity (§4.1.4 flow-limit matrix).

Honest scope: one process, so this is traffic shaping for a single instance, not a
distributed quota. Redis-backed limits arrive with M6 behind the same Bucket/check seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .clock import Clock, SystemClock
from .metrics import ResilienceMetrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..settings import RateLimitSettings


class Bucket(StrEnum):
    GENERAL = "general"
    READ = "read"
    ANSWER = "answer"
    HEAVY = "heavy"
    AI_CALL = "ai_call"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    bucket: Bucket
    retry_after: float
    remaining: int
    capacity: int


class TokenBucket:
    """Classic token bucket: capacity = burst, refill = rate per second on the clock."""

    def __init__(self, *, rate: float, capacity: float, clock: Clock) -> None:
        self.rate = max(rate, 1e-9)
        self.capacity = max(capacity, 1.0)
        self._clock = clock
        self._tokens = self.capacity
        self._updated = clock.now()

    def take(self) -> tuple[bool, float, int]:
        now = self._clock.now()
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._updated = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True, 0.0, int(self._tokens)
        return False, (1.0 - self._tokens) / self.rate, 0

    @property
    def idle(self) -> bool:
        """True when the bucket would be full right now (safe to forget)."""
        elapsed = max(0.0, self._clock.now() - self._updated)
        projected = min(self.capacity, self._tokens + elapsed * self.rate)
        return projected >= self.capacity - 1e-9


class RateLimiter:
    def __init__(
        self,
        settings: RateLimitSettings,
        *,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
        max_identities: int = 10_000,
    ) -> None:
        self._settings = settings
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._max_identities = max(1, max_identities)
        self._buckets: dict[tuple[Bucket, str], TokenBucket] = {}

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def tracked_identities(self) -> int:
        return len(self._buckets)

    def rate_for(self, bucket: Bucket) -> float:
        return {
            Bucket.GENERAL: self._settings.general_per_second,
            Bucket.READ: self._settings.read_per_second,
            Bucket.ANSWER: self._settings.answer_per_second,
            Bucket.HEAVY: self._settings.heavy_per_second,
            Bucket.AI_CALL: self._settings.ai_call_per_second,
        }[bucket]

    def check(self, bucket: Bucket, identity: str) -> RateLimitDecision:
        rate = self.rate_for(bucket)
        capacity = max(1, round(rate * self._settings.burst_multiplier))
        entry = self._buckets.get((bucket, identity))
        if entry is None:
            self._make_room()
            entry = TokenBucket(rate=rate, capacity=capacity, clock=self._clock)
            self._buckets[(bucket, identity)] = entry

        allowed, retry_after, remaining = entry.take()
        if not allowed:
            self._metrics.rate_limited += 1
        return RateLimitDecision(
            allowed=allowed,
            bucket=bucket,
            retry_after=retry_after,
            remaining=remaining,
            capacity=capacity,
        )

    def _make_room(self) -> None:
        if len(self._buckets) < self._max_identities:
            return
        # Lazy eviction: only buckets that have fully refilled are safe to forget.
        for key, entry in list(self._buckets.items()):
            if entry.idle:
                self._buckets.pop(key, None)
            if len(self._buckets) < self._max_identities:
                return
