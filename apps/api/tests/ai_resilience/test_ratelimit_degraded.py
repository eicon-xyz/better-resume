"""P7 / D19: what happens when the shared (Redis) bucket store is unavailable.

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
    ManualClock,
    RateLimiter,
    ResilienceMetrics,
)
from better_resume.settings import RateLimitSettings


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


def _limiter(
    clock: ManualClock,
    metrics: ResilienceMetrics,
    store: _FlakyStore,
    *,
    cooldown: float = 30.0,
) -> RateLimiter:
    from better_resume.ai_resilience import DegradingBucketStore, InProcessBucketStore

    degrading = DegradingBucketStore(
        primary=store,
        fallback=InProcessBucketStore(clock=clock),
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
    limiter = _limiter(clock, metrics, store)

    decision = await limiter.check(Bucket.AI_CALL, "session:a")

    assert decision.allowed is True  # 请求仍然被服务：不变成 503
    assert decision.scope is BucketScope.INSTANCE  # 但配额退回本副本（D19）
    assert metrics.snapshot()["rate_limit_degraded"] == 1


async def test_degraded_calls_skip_redis_until_the_cooldown_expires() -> None:
    clock, metrics, store = ManualClock(), ResilienceMetrics(), _FlakyStore()
    limiter = _limiter(clock, metrics, store, cooldown=30.0)

    await limiter.check(Bucket.AI_CALL, "session:a")  # 第一次失败 → 进降级
    for _ in range(5):
        await limiter.check(Bucket.AI_CALL, "session:a")

    assert store.calls == 1  # 冷却窗口内一次都不打 Redis（不给请求叠 socket 超时）

    clock.advance(31)
    await limiter.check(Bucket.AI_CALL, "session:a")
    assert store.calls == 2  # 窗口过了，再试一次


async def test_recovery_returns_to_the_shared_bucket() -> None:
    clock, metrics, store = ManualClock(), ResilienceMetrics(), _FlakyStore()
    limiter = _limiter(clock, metrics, store, cooldown=30.0)

    assert (await limiter.check(Bucket.AI_CALL, "session:a")).scope is BucketScope.INSTANCE

    store.down = False
    clock.advance(31)
    decision = await limiter.check(Bucket.AI_CALL, "session:a")

    assert decision.scope is BucketScope.SHARED
    assert decision.remaining == 9
