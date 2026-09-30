"""Token buckets per route class and identity (§4.1.4 flow-limit matrix).

The bucket maths is the M3 token bucket; **where the state lives is a seam**
(`BucketStore`): the in-process dict (default, and the fallback when Redis is down) or
Redis for a quota shared by every replica (P7 / D19). The Redis store lives in
`redis_buckets.py`; the degradation policy lives in `ai_resilience.degraded`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

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


class BucketScope(StrEnum):
    """Where the decision was made — surfaced to clients via X-RateLimit-Scope.

    SHARED: Redis held the quota (every replica counts against one bucket).
    INSTANCE: this process held it — either by configuration, or because the shared
    store was unavailable and we degraded (see D19).
    """

    SHARED = "shared"
    INSTANCE = "instance"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    bucket: Bucket
    retry_after: float
    remaining: int
    capacity: int
    scope: BucketScope = BucketScope.INSTANCE


@runtime_checkable
class BucketStore(Protocol):
    """One atomic "take a token" — the only thing the limiter needs from a backend."""

    #: Where this store judges quotas; a degrading store flips it at runtime (D19).
    scope: BucketScope

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]: ...

    @property
    def tracked(self) -> int: ...

    async def aclose(self) -> None: ...


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


class InProcessBucketStore:
    """Per-process buckets: today's behaviour, and the degraded fallback (D19)."""

    scope = BucketScope.INSTANCE

    def __init__(self, *, clock: Clock, max_identities: int = 10_000) -> None:
        self._clock = clock
        self._max_identities = max(1, max_identities)
        self._buckets: dict[str, TokenBucket] = {}

    @property
    def tracked(self) -> int:
        return len(self._buckets)

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        entry = self._buckets.get(key)
        if entry is None:
            self._make_room()
            entry = TokenBucket(rate=rate, capacity=capacity, clock=self._clock)
            self._buckets[key] = entry
        return entry.take()

    async def aclose(self) -> None:
        self._buckets.clear()

    def _make_room(self) -> None:
        if len(self._buckets) < self._max_identities:
            return
        # Lazy eviction: only buckets that have fully refilled are safe to forget.
        for key, entry in list(self._buckets.items()):
            if entry.idle:
                self._buckets.pop(key, None)
            if len(self._buckets) < self._max_identities:
                return


class RateLimiter:
    """Per-identity, per-route-class limiting over a `BucketStore`."""

    def __init__(
        self,
        settings: RateLimitSettings,
        *,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
        max_identities: int = 10_000,
        store: BucketStore | None = None,
        stores: dict[Bucket, BucketStore] | None = None,
    ) -> None:
        self._settings = settings
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._default: BucketStore = store or InProcessBucketStore(
            clock=self._clock, max_identities=max_identities
        )
        #: Per-bucket overrides — the cost buckets may live in a shared store (P7 / D19).
        self._stores: dict[Bucket, BucketStore] = dict(stores or {})

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def tracked_identities(self) -> int:
        return sum(store.tracked for store in self._unique_stores())

    @property
    def metrics(self) -> ResilienceMetrics:
        return self._metrics

    @property
    def store(self) -> BucketStore:
        """The default store — what every bucket uses unless it has an override."""
        return self._default

    def store_for(self, bucket: Bucket) -> BucketStore:
        return self._stores.get(bucket, self._default)

    def _unique_stores(self) -> list[BucketStore]:
        seen: dict[int, BucketStore] = {}
        for store in (self._default, *self._stores.values()):
            seen.setdefault(id(store), store)
        return list(seen.values())

    def rate_for(self, bucket: Bucket) -> float:
        return {
            Bucket.GENERAL: self._settings.general_per_second,
            Bucket.READ: self._settings.read_per_second,
            Bucket.ANSWER: self._settings.answer_per_second,
            Bucket.HEAVY: self._settings.heavy_per_second,
            Bucket.AI_CALL: self._settings.ai_call_per_second,
        }[bucket]

    def capacity_for(self, bucket: Bucket) -> int:
        return max(1, round(self.rate_for(bucket) * self._settings.burst_multiplier))

    @staticmethod
    def key_for(bucket: Bucket, identity: str) -> str:
        """One namespace for both stores: `bucket|identity` (Redis prefixes it)."""
        return f"{bucket.value}|{identity}"

    async def check(self, bucket: Bucket, identity: str) -> RateLimitDecision:
        rate = self.rate_for(bucket)
        capacity = self.capacity_for(bucket)
        store = self.store_for(bucket)
        allowed, retry_after, remaining = await store.take(
            self.key_for(bucket, identity), rate=rate, capacity=capacity
        )
        if not allowed:
            self._metrics.rate_limited += 1
        return RateLimitDecision(
            allowed=allowed,
            bucket=bucket,
            retry_after=retry_after,
            remaining=remaining,
            capacity=capacity,
            scope=store.scope,
        )

    async def aclose(self) -> None:
        for store in self._unique_stores():
            await store.aclose()
