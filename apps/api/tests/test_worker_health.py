"""M6-T5: the worker publishes a heartbeat so compose can health-check it.

A queue worker has no port to poll, so `serve` refreshes a short-lived Redis key and the
container health check (`python -m better_resume.worker --health`) reads it.
"""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis

from better_resume.settings import Settings
from better_resume.worker import beat, check_health, heartbeat_key, serve


@pytest.fixture
def worker_settings(settings: Settings, redis_url: str) -> Settings:
    return settings.model_copy(
        update={
            "redis_url": redis_url,
            "jobs_enabled": True,
            "jobs_stream": f"br:jobs:health:{id(settings):x}",
            "jobs_heartbeat_ttl_seconds": 30,
        }
    )


async def test_beat_publishes_a_heartbeat_with_a_ttl(worker_settings: Settings) -> None:
    key = heartbeat_key(worker_settings)
    client = aioredis.from_url(worker_settings.redis_url, decode_responses=True)
    try:
        await beat(client, key=key, consumer="worker-1", ttl_seconds=30)

        assert await client.get(key) == "worker-1"
        assert 0 < await client.ttl(key) <= 30
    finally:
        await client.aclose()


async def test_check_health_is_false_without_a_heartbeat(worker_settings: Settings) -> None:
    client = aioredis.from_url(worker_settings.redis_url, decode_responses=True)
    try:
        await client.delete(heartbeat_key(worker_settings))
    finally:
        await client.aclose()

    assert await check_health(worker_settings) is False


async def test_serve_survives_a_redis_timeout_in_the_heartbeat(
    worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-D/P26: during a Redis failover the heartbeat write times out; the worker must log,
    back off and keep going — not exit (observed live: exit 1 during master→replica promotion,
    which silently stopped every background job until someone restarted the container)."""
    from redis.exceptions import TimeoutError as RedisTimeoutError

    from better_resume import worker as worker_module

    calls = {"beat": 0}

    async def flaky_beat(client, *, key, consumer, ttl_seconds):  # noqa: ANN001, ANN202
        calls["beat"] += 1
        if calls["beat"] == 1:
            raise RedisTimeoutError("Timeout reading from redis:6379")
        await worker_module.beat(client, key=key, consumer=consumer, ttl_seconds=ttl_seconds)

    monkeypatch.setattr(worker_module, "beat", flaky_beat)
    stop = asyncio.Event()
    task = asyncio.create_task(serve(worker_settings, stop=stop))
    try:
        for _ in range(40):
            if calls["beat"] >= 2:
                break
            await asyncio.sleep(0.1)
        assert calls["beat"] >= 2, "the worker stopped beating after the first failure"
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)  # must not raise


async def test_check_health_is_false_when_redis_is_unreachable(worker_settings: Settings) -> None:
    """P2 coverage: during a failover the container health check hits an unreachable
    Redis; that must read as unhealthy, never raise out of the healthcheck process."""
    down = worker_settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"})
    assert await check_health(down) is False


async def _heartbeat_value(settings: Settings) -> str | None:
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        return await client.get(heartbeat_key(settings))
    finally:
        await client.aclose()


async def test_serve_refreshes_the_heartbeat_while_it_runs(worker_settings: Settings) -> None:
    client = aioredis.from_url(worker_settings.redis_url, decode_responses=True)
    try:
        await client.delete(heartbeat_key(worker_settings))
    finally:
        await client.aclose()

    stop = asyncio.Event()
    task = asyncio.create_task(serve(worker_settings, stop=stop))
    seen = ""
    try:
        for _ in range(20):  # the loop beats before it blocks on the stream
            seen = await _heartbeat_value(worker_settings) or ""
            if seen:
                break
            await asyncio.sleep(0.1)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert seen.startswith("worker-")
    # A clean stop drops the key, so the health check flips without waiting for the TTL.
    assert await _heartbeat_value(worker_settings) is None
