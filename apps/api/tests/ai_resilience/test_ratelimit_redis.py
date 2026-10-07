"""P7: the shared bucket store on real Redis (two "replicas", one quota).

Redis is the system boundary here, so it is not faked — the test skips when it is
unreachable (same rule as tests/test_distributed_flight.py). Time is injected
(`ManualWallClock`): token refill is asserted by advancing the clock, never by sleeping.
"""

from __future__ import annotations

import uuid

import pytest
from redis import exceptions as redis_exceptions

from better_resume.ai_resilience import ManualWallClock
from better_resume.settings import Settings


@pytest.fixture
def redis_url() -> str:
    return Settings(_env_file=None).redis_url


def _identity() -> str:
    return "ai_call|session:" + uuid.uuid4().hex  # 每个用例一套键，免得互相踩


@pytest.fixture
async def stores(redis_url: str):
    from better_resume.ai_resilience import RedisBucketStore

    started = 1_700_000_000_000
    first = RedisBucketStore(redis_url, clock=ManualWallClock(started))
    second = RedisBucketStore(redis_url, clock=ManualWallClock(started))
    try:
        await first.ping()
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    try:
        yield first, second
    finally:
        await first.aclose()
        await second.aclose()


async def test_two_replicas_share_one_quota(stores) -> None:
    """两个副本、同一身份：合计放行数 = capacity，不是 2 × capacity。"""
    first, second = stores
    key = _identity()
    allowed = 0
    for index in range(8):
        store = first if index % 2 == 0 else second
        decision, _, _ = await store.take(key, rate=0.0001, capacity=4.0)
        allowed += int(decision)

    assert allowed == 4


async def test_tokens_refill_on_the_injected_wall_clock(stores) -> None:
    """令牌恢复由注入的 wall-clock 驱动——不写真实 sleep 断言。"""
    first, _ = stores
    key = _identity()

    assert (await first.take(key, rate=2.0, capacity=2.0))[0] is True
    assert (await first.take(key, rate=2.0, capacity=2.0))[0] is True

    allowed, retry_after, remaining = await first.take(key, rate=2.0, capacity=2.0)
    assert allowed is False
    assert retry_after == pytest.approx(0.5, abs=0.02)  # 2/s → 一个令牌 500ms
    assert remaining == 0

    first.clock.advance_ms(500)
    assert (await first.take(key, rate=2.0, capacity=2.0))[0] is True


async def test_the_bucket_key_carries_a_ttl(stores) -> None:
    """TTL 就是"闲置桶自动遗忘"——取代进程内的 max_identities 懒淘汰。"""
    first, _ = stores
    key = _identity()

    await first.take(key, rate=2.0, capacity=4.0)
    ttl_ms = await first.pttl(key)

    assert 0 < ttl_ms <= 60_000  # 满桶恢复 ≈ 2s，下限 60s
