"""M6-T1: Redis question locks — mutex, lease, takeover safety, bounded wait."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from redis import exceptions as redis_exceptions

from better_resume.interview_engine import (
    QuestionLockRegistry,
    QuestionLockTimeout,
    RedisQuestionLockRegistry,
)
from better_resume.settings import Settings


@pytest.fixture
def redis_url() -> str:
    return Settings(_env_file=None).redis_url


@pytest.fixture
async def locks(redis_url: str):
    registry = RedisQuestionLockRegistry(
        redis_url, ttl_seconds=5.0, wait_seconds=2.0, poll_seconds=0.01
    )
    try:
        await registry._client.ping()  # noqa: SLF001 - skip cleanly when Redis is absent
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    yield registry
    await registry._client.flushdb()
    await registry.aclose()


def token_key(registry: RedisQuestionLockRegistry, session: str, question: str) -> str:
    return registry.key(session, question)


async def test_lock_is_mutually_exclusive(locks: RedisQuestionLockRegistry) -> None:
    session = uuid.uuid4().hex
    order: list[str] = []
    inside = 0
    peak = 0

    async def worker(name: str) -> None:
        nonlocal inside, peak
        async with locks.acquire(session, "1"):
            inside += 1
            peak = max(peak, inside)
            order.append(f"{name}:enter")
            await asyncio.sleep(0.02)
            order.append(f"{name}:exit")
            inside -= 1

    await asyncio.gather(*(worker(name) for name in ("a", "b", "c")))

    assert peak == 1
    # enter/exit must alternate: no interleaving inside the critical section
    assert [entry.split(":")[1] for entry in order] == [
        "enter",
        "exit",
        "enter",
        "exit",
        "enter",
        "exit",
    ]


async def test_different_questions_do_not_block(locks: RedisQuestionLockRegistry) -> None:
    session = uuid.uuid4().hex
    both_inside = asyncio.Event()
    release = asyncio.Event()
    inside = 0

    async def worker(question: str) -> None:
        nonlocal inside
        async with locks.acquire(session, question):
            inside += 1
            if inside == 2:
                both_inside.set()
            await release.wait()

    tasks = [asyncio.create_task(worker(q)) for q in ("1", "2")]
    await asyncio.wait_for(both_inside.wait(), timeout=2.0)
    release.set()
    await asyncio.gather(*tasks)
    assert inside == 2


async def test_bounded_wait_raises_a_clear_error(locks: RedisQuestionLockRegistry) -> None:
    session = uuid.uuid4().hex
    holder_ready = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with locks.acquire(session, "1"):
            holder_ready.set()
            await release.wait()

    holding = asyncio.create_task(holder())
    await holder_ready.wait()

    with pytest.raises(QuestionLockTimeout, match="locked by another worker"):
        async with locks.acquire(session, "1"):
            pass  # pragma: no cover - never reached

    release.set()
    await holding


async def test_exception_inside_releases_the_lock(locks: RedisQuestionLockRegistry) -> None:
    session = uuid.uuid4().hex

    with pytest.raises(RuntimeError):
        async with locks.acquire(session, "1"):
            raise RuntimeError("boom")

    async with locks.acquire(session, "1"):
        pass  # acquired again: the lock was released


async def test_cancellation_releases_and_leaves_no_task(locks: RedisQuestionLockRegistry) -> None:
    session = uuid.uuid4().hex
    entered = asyncio.Event()

    async def hold() -> None:
        async with locks.acquire(session, "1"):
            entered.set()
            await asyncio.sleep(30)

    task = asyncio.create_task(hold())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async with locks.acquire(session, "1"):
        pass
    assert not [
        t for t in asyncio.all_tasks() if t.get_name() == "redis-lock-renew" and not t.done()
    ]


async def test_lease_expires_after_a_crash(redis_url: str) -> None:
    """A dead holder must not block the question forever (short real TTL)."""
    registry = RedisQuestionLockRegistry(redis_url, ttl_seconds=0.1, wait_seconds=2.0)
    try:
        await registry._client.ping()  # noqa: SLF001
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    session = uuid.uuid4().hex
    try:
        await registry._client.set(token_key(registry, session, "1"), "dead-owner", px=100)
        await asyncio.sleep(0.15)
        async with registry.acquire(session, "1"):
            pass
    finally:
        await registry._client.flushdb()
        await registry.aclose()


async def test_lease_is_renewed_while_held(redis_url: str) -> None:
    registry = RedisQuestionLockRegistry(redis_url, ttl_seconds=0.2, wait_seconds=2.0)
    try:
        await registry._client.ping()  # noqa: SLF001
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    session = uuid.uuid4().hex
    try:
        async with registry.acquire(session, "1"):
            await asyncio.sleep(0.45)  # two TTLs: without renewal this would expire
            assert await registry._client.get(token_key(registry, session, "1")) is not None
    finally:
        await registry._client.flushdb()
        await registry.aclose()


async def test_stale_owner_never_deletes_a_taken_over_lock(redis_url: str) -> None:
    registry = RedisQuestionLockRegistry(redis_url, ttl_seconds=0.1, wait_seconds=1.0)
    try:
        await registry._client.ping()  # noqa: SLF001
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    session = uuid.uuid4().hex
    try:
        await registry._client.set(token_key(registry, session, "1"), "new-owner", px=5000)
        await registry._release(token_key(registry, session, "1"), "stale-owner")

        assert await registry._client.get(token_key(registry, session, "1")) == "new-owner"
    finally:
        await registry._client.flushdb()
        await registry.aclose()


async def test_fifty_concurrent_answers_enter_one_at_a_time(
    locks: RedisQuestionLockRegistry,
) -> None:
    session = uuid.uuid4().hex
    counter = 0
    peak = 0

    async def attempt() -> None:
        nonlocal counter, peak
        async with locks.acquire(session, "1"):
            counter += 1
            peak = max(peak, counter)
            await asyncio.sleep(0)
            counter -= 1

    await asyncio.gather(*(attempt() for _ in range(50)))

    assert peak == 1


async def test_memory_backend_keeps_m2_behaviour() -> None:
    registry = QuestionLockRegistry()
    order: list[str] = []

    async def worker(name: str) -> None:
        async with registry.acquire("s", "1"):
            order.append(f"{name}:enter")
            await asyncio.sleep(0)
            order.append(f"{name}:exit")

    await asyncio.gather(worker("a"), worker("b"))
    assert [entry.split(":")[1] for entry in order] == ["enter", "exit", "enter", "exit"]
    assert registry.active_keys() == []
