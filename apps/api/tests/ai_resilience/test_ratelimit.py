"""M3-T6: token buckets on the manual clock (unit level).

P7: `RateLimiter.check` is async now — the bucket may live in Redis, so the seam is a
coroutine from the start and the in-process store is just one implementation of it.
"""

from __future__ import annotations

import pytest

from better_resume.ai_resilience import (
    Bucket,
    BucketScope,
    ManualClock,
    RateLimiter,
    TokenBucket,
)
from better_resume.settings import RateLimitSettings


def test_defaults_are_calibrated_for_real_traffic() -> None:
    """P1-B 标定（2026-09-15，证据 docs/perf/M6-capacity.md §2.7）。

    实测：真实单用户峰值 ~0.5 rps（一条流 2-4s）；AI_CALL 6/s 曾允许单身份经 2 副本
    维持 24 并发供应商流。收紧到 2/s（burst 4/副本 → 2 副本 8 并发，4× 余量）；
    answer 8/s → 2/s（真实提交 ~0.2 rps，10× 余量）。general/read/heavy 无供应商
    成本压力信号，维持不变；burst_multiplier 维持 2.0。

    P7 起配额改为跨副本共享（D19），"2 副本 8 并发"要读成"合计 burst 4"——见
    `docs/perf/M6-capacity.md` §2.7 的迁移说明。
    """
    settings = RateLimitSettings()
    assert settings.ai_call_per_second == 2.0
    assert settings.answer_per_second == 2.0
    assert settings.general_per_second == 20.0
    assert settings.read_per_second == 15.0
    assert settings.heavy_per_second == 2.0
    assert settings.burst_multiplier == 2.0


def test_bucket_allows_the_burst_then_refills_over_time() -> None:
    clock = ManualClock()
    bucket = TokenBucket(rate=2.0, capacity=2.0, clock=clock)

    assert bucket.take()[0] is True
    assert bucket.take()[0] is True

    allowed, retry_after, remaining = bucket.take()
    assert allowed is False
    assert retry_after == pytest.approx(0.5)  # one token at 2/s
    assert remaining == 0

    clock.advance(0.5)
    assert bucket.take()[0] is True


def test_bucket_caps_refill_at_capacity() -> None:
    clock = ManualClock()
    bucket = TokenBucket(rate=1.0, capacity=2.0, clock=clock)
    clock.advance(100.0)
    assert bucket.take()[0] is True
    assert bucket.take()[0] is True
    assert bucket.take()[0] is False
    assert bucket.idle is False


async def test_limiter_uses_the_settings_matrix() -> None:
    clock = ManualClock()
    settings = RateLimitSettings(
        general_per_second=20.0,
        read_per_second=15.0,
        ai_call_per_second=6.0,
        burst_multiplier=1.0,
    )
    limiter = RateLimiter(settings, clock=clock)

    assert limiter.rate_for(Bucket.READ) == 15.0
    assert (await limiter.check(Bucket.AI_CALL, "session:other")).capacity == 6
    for _ in range(6):
        assert (await limiter.check(Bucket.AI_CALL, "session:abc")).allowed is True

    blocked = await limiter.check(Bucket.AI_CALL, "session:abc")
    assert blocked.allowed is False
    assert blocked.retry_after == pytest.approx(1 / 6)
    assert limiter._metrics.snapshot()["rate_limited"] == 1  # noqa: SLF001 - test hook


async def test_identities_and_buckets_are_isolated() -> None:
    clock = ManualClock()
    limiter = RateLimiter(RateLimitSettings(read_per_second=1.0, burst_multiplier=1.0), clock=clock)

    assert (await limiter.check(Bucket.READ, "session:a")).allowed is True
    assert (await limiter.check(Bucket.READ, "session:a")).allowed is False
    assert (await limiter.check(Bucket.READ, "session:b")).allowed is True  # other identity
    assert (await limiter.check(Bucket.GENERAL, "session:a")).allowed is True  # other bucket


async def test_full_registry_evicts_idle_buckets() -> None:
    clock = ManualClock()
    limiter = RateLimiter(
        RateLimitSettings(read_per_second=1.0, burst_multiplier=1.0),
        clock=clock,
        max_identities=2,
    )

    await limiter.check(Bucket.READ, "a")
    clock.advance(10)  # bucket "a" refills completely
    await limiter.check(Bucket.READ, "b")
    await limiter.check(Bucket.READ, "c")

    assert limiter.tracked_identities <= 2


def test_disabled_settings_report_disabled() -> None:
    limiter = RateLimiter(RateLimitSettings(enabled=False))
    assert limiter.enabled is False


class _SharedStore:
    """边界 fake：一个"共享"后端（今天由 Redis 承担），不入库任何判定逻辑。"""

    scope = BucketScope.SHARED

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, float]] = []

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        self.calls.append((key, rate, capacity))
        return True, 0.0, 3

    @property
    def tracked(self) -> int:
        return len(self.calls)

    async def aclose(self) -> None:
        return None


async def test_decision_reports_where_the_quota_was_judged() -> None:
    """P7：客户端要能看出这一票是"共享配额"还是"本副本配额"（D19 的可观测性要求）。"""
    settings = RateLimitSettings(ai_call_per_second=2.0, burst_multiplier=2.0)
    shared = _SharedStore()
    limiter = RateLimiter(settings, clock=ManualClock(), store=shared)

    decision = await limiter.check(Bucket.AI_CALL, "session:abc")

    assert decision.scope is BucketScope.SHARED
    assert decision.remaining == 3
    assert shared.calls == [("ai_call|session:abc", 2.0, 4.0)]

    instance_limiter = RateLimiter(settings, clock=ManualClock())
    assert (
        await instance_limiter.check(Bucket.AI_CALL, "session:abc")
    ).scope is BucketScope.INSTANCE
