"""P7 / D19: which buckets are shared, and what happens when Redis is not there.

Q2's decision: only the vendor-cost buckets (AI_CALL / ANSWER / HEAVY) get the shared
quota — they cap what we spend upstream. GENERAL / READ cap *our own* capacity, which grows
with the number of replicas, so per-replica limiting is the correct semantics for them
(and keeps the cheap GET path off Redis entirely).
"""

from __future__ import annotations

import pytest

from better_resume.ai_resilience import Bucket, BucketScope, ManualClock
from better_resume.settings import RateLimitSettings, Settings


def _settings(**overrides: object) -> Settings:
    from better_resume.settings import RateLimitSettings as RL

    values = {
        "backend": "redis",
        "shared_buckets": "ai_call,answer,heavy",
        "redis_socket_timeout_ms": 50,
        "degraded_cooldown_seconds": 30.0,
    }
    values.update(overrides)
    # 端口 6399 上没有任何东西：连接立即被拒，不需要等超时
    return Settings(_env_file=None, redis_url="redis://127.0.0.1:6399/0", rate_limit=RL(**values))


async def test_only_the_cost_buckets_are_shared() -> None:
    from better_resume.ai_resilience import build_rate_limiter

    limiter = build_rate_limiter(_settings(), clock=ManualClock())

    for bucket in (Bucket.AI_CALL, Bucket.ANSWER, Bucket.HEAVY):
        assert limiter.store_for(bucket).scope is BucketScope.SHARED, bucket
    for bucket in (Bucket.GENERAL, Bucket.READ):
        assert limiter.store_for(bucket).scope is BucketScope.INSTANCE, bucket

    await limiter.aclose()


async def test_an_unreachable_redis_degrades_the_cost_buckets_only() -> None:
    from better_resume.ai_resilience import build_rate_limiter

    limiter = build_rate_limiter(_settings(), clock=ManualClock())

    cost = await limiter.check(Bucket.AI_CALL, "session:a")
    assert cost.allowed is True  # 请求照样被服务（D19：不变成 503）
    assert cost.scope is BucketScope.INSTANCE  # 退回本副本配额

    cheap = await limiter.check(Bucket.READ, "session:a")
    assert cheap.scope is BucketScope.INSTANCE

    snapshot = limiter.metrics.snapshot()
    assert snapshot["rate_limit_degraded"] == 1  # 只有走到共享后端的那一票被记为降级
    assert snapshot["rate_limited"] == 0

    await limiter.aclose()


async def test_the_memory_backend_never_touches_redis() -> None:
    from better_resume.ai_resilience import build_rate_limiter

    limiter = build_rate_limiter(_settings(backend="memory"), clock=ManualClock())

    for bucket in Bucket:
        assert limiter.store_for(bucket).scope is BucketScope.INSTANCE
    assert (await limiter.check(Bucket.AI_CALL, "session:a")).scope is BucketScope.INSTANCE
    assert limiter.metrics.snapshot()["rate_limit_degraded"] == 0

    await limiter.aclose()


def test_shared_buckets_reject_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown bucket"):
        RateLimitSettings(backend="redis", shared_buckets="ai_call,nope")
