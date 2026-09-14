"""M6-T4/T5: the worker loop must survive Redis hiccups and stop cleanly.

The T5 drill found this the hard way: a blocked XREADGROUP read that is cancelled during
shutdown surfaced as a redis TimeoutError, the exception escaped `serve`, the container
exited and the queued job stayed queued forever.
"""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis
from redis.exceptions import TimeoutError as RedisTimeoutError

from better_resume import worker
from better_resume.jobs.queue import JobQueue
from better_resume.settings import Settings


@pytest.fixture
def worker_settings(settings: Settings, redis_url: str) -> Settings:
    return settings.model_copy(
        update={
            "redis_url": redis_url,
            "jobs_enabled": True,
            "jobs_stream": f"br:jobs:loop:{id(settings):x}",
        }
    )


class _Closable:
    async def aclose(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


def _stub_runtime() -> dict:
    return {"resilience": _Closable(), "engine": _Closable()}


def test_queue_socket_timeout_outlives_a_blocking_read(worker_settings: Settings) -> None:
    queue = JobQueue(
        worker_settings.redis_url,
        stream=worker_settings.jobs_stream,
        socket_timeout_seconds=15.0,
    )

    kwargs = queue._client.connection_pool.connection_kwargs  # noqa: SLF001 - the seam under test
    assert kwargs["socket_timeout"] == 15.0
    assert queue.blocking_block_ms(requested_ms=500) == 500
    # A caller asking for a longer block than the socket allows must be capped, not truncated.
    assert queue.blocking_block_ms(requested_ms=60_000) < 15_000


async def test_serve_keeps_looping_after_a_transient_redis_error(
    worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    stop = asyncio.Event()

    async def flaky_run_once(queue, runtime, *, consumer, block_ms=500):  # noqa: ANN001, ANN202
        calls.append(consumer)
        if len(calls) == 1:
            raise RedisTimeoutError("Timeout reading from redis:6379")
        stop.set()
        return 0

    monkeypatch.setattr(worker, "run_once", flaky_run_once)
    monkeypatch.setattr(worker, "build_worker_runtime", lambda settings: _stub_runtime())

    # Must return normally (no exception) even though the first call blew up.
    await asyncio.wait_for(worker.serve(worker_settings, stop=stop), timeout=15)

    assert len(calls) >= 2, "the loop stopped after the first error"


async def test_serve_drops_the_heartbeat_on_a_clean_stop(worker_settings: Settings) -> None:
    stop = asyncio.Event()
    stop.set()

    await asyncio.wait_for(worker.serve(worker_settings, stop=stop), timeout=10)

    client = aioredis.from_url(worker_settings.redis_url, decode_responses=True)
    try:
        assert await client.get(worker.heartbeat_key(worker_settings)) is None
    finally:
        await client.aclose()


def test_serve_loop_backoff_is_bounded() -> None:
    assert worker.loop_backoff_seconds(1) <= worker.loop_backoff_seconds(2)
    assert worker.loop_backoff_seconds(50) <= 5.0
