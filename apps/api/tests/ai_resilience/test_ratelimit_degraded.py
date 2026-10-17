"""what happens when the shared (Redis) bucket store is unavailable.

The decision recorded in D19: an unavailable shared store must NOT become a 503 and must
NOT silently lift the limit. It degrades to the per-replica bucket — i.e. exactly the
semantics shipped before P7 — and stops touching Redis for a cooldown window so a blink
does not add a socket timeout to every request. Redis is faked at the boundary only.
"""

from __future__ import annotations

from redis import exceptions as redis_exceptions

from better_resume.ai_resilience import (
    Bucket,
    BucketScope,
    Clock,
    DegradingBucketStore,
    InProcessBucketStore,
    ManualClock,
    RateLimitDecision,
    RateLimiter,
    ResilienceMetrics,
)
from better_resume.settings import RateLimitSettings

#: D19 serves a degraded request; a store error reaching the caller is not a degradation.
_ESCAPED = "the shared-store error escaped instead of degrading to the instance bucket"


class _FlakyStore:
    """Boundary fake: projects "Redis is unreachable" as an exception, nothing else."""

    scope = BucketScope.SHARED

    def __init__(self, *, down: bool = True) -> None:
        self.calls = 0
        self.down = down

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        self.calls += 1
        if self.down:
            raise redis_exceptions.ConnectionError("redis is unreachable")
        return True, 0.0, 9

    @property
    def tracked(self) -> int:
        return 0

    async def aclose(self) -> None:
        return None


class _RecordingBucketStore(InProcessBucketStore):
    """The real in-process bucket, plus a record of the takes it served (D19 evidence)."""

    def __init__(self, *, clock: Clock) -> None:
        super().__init__(clock=clock)
        self.taken: list[tuple[str, float, float]] = []

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        self.taken.append((key, rate, capacity))
        return await super().take(key, rate=rate, capacity=capacity)


async def _check(limiter: RateLimiter) -> RateLimitDecision | None:
    """One limited call: None means the store error escaped instead of being degraded."""
    try:
        return await limiter.check(Bucket.AI_CALL, "session:a")
    except redis_exceptions.ConnectionError:
        return None


def _limiter(
    clock: ManualClock,
    metrics: ResilienceMetrics,
    store: _FlakyStore,
    *,
    cooldown: float = 30.0,
    fallback: InProcessBucketStore | None = None,
) -> RateLimiter:
    degrading = DegradingBucketStore(
        primary=store,
        fallback=fallback or InProcessBucketStore(clock=clock),
        cooldown_seconds=cooldown,
        clock=clock,
        metrics=metrics,
    )
    return RateLimiter(
        RateLimitSettings(ai_call_per_second=2.0, burst_multiplier=2.0),
        clock=clock,
        metrics=metrics,
        store=degrading,
    )


async def test_a_failing_shared_store_degrades_to_the_instance_bucket() -> None:
    clock, metrics, store = ManualClock(), ResilienceMetrics(), _FlakyStore()
    fallback = _RecordingBucketStore(clock=clock)
    limiter = _limiter(clock, metrics, store, fallback=fallback)

    decision = await _check(limiter)

    assert decision is not None, _ESCAPED
    # 回退真的发生了：本副本桶被 take，入参就是限流器算出来的 key/rate/capacity
    assert fallback.taken == [("ai_call|session:a", 2.0, 4)]
    assert decision.allowed is True  # 请求仍然被服务：不变成 503
    assert decision.scope is BucketScope.INSTANCE  # 但配额退回本副本（D19）
    assert metrics.snapshot()["rate_limit_degraded"] == 1


async def test_degraded_calls_skip_redis_until_the_cooldown_expires() -> None:
    clock, metrics, store = ManualClock(), ResilienceMetrics(), _FlakyStore()
    limiter = _limiter(clock, metrics, store, cooldown=30.0)

    assert await _check(limiter) is not None, _ESCAPED  # 第一次失败 → 进降级
    for _ in range(5):
        assert await _check(limiter) is not None, _ESCAPED

    assert store.calls == 1  # 冷却窗口内一次都不打 Redis（不给请求叠 socket 超时）

    clock.advance(31)
    assert await _check(limiter) is not None, _ESCAPED
    assert store.calls == 2  # 窗口过了，再试一次


async def test_recovery_returns_to_the_shared_bucket() -> None:
    clock, metrics, store = ManualClock(), ResilienceMetrics(), _FlakyStore()
    limiter = _limiter(clock, metrics, store, cooldown=30.0)

    first = await _check(limiter)
    assert first is not None, _ESCAPED
    assert first.scope is BucketScope.INSTANCE

    store.down = False
    clock.advance(31)
    decision = await _check(limiter)

    assert decision is not None, _ESCAPED
    assert decision.scope is BucketScope.SHARED
    assert decision.remaining == 9
