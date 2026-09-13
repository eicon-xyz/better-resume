"""M3-T2: in-process single flight — concurrent same key runs the vendor once."""

from __future__ import annotations

import asyncio

import pytest

from better_resume.ai_resilience import (
    AiInvalid,
    AiTimeout,
    DirectAiResilience,
    ManualClock,
    SingleFlight,
    Stage,
)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def flight(clock: ManualClock) -> SingleFlight:
    return SingleFlight(clock=clock, max_entries=8)


async def test_concurrent_same_key_runs_once(flight: SingleFlight) -> None:
    calls = 0
    release = asyncio.Event()

    async def fn() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "answer"

    tasks = [asyncio.create_task(flight.execute("k", fn)) for _ in range(10)]
    for _ in range(3):
        await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(*tasks) == ["answer"] * 10
    assert calls == 1
    snapshot = flight.metrics.snapshot()
    assert snapshot["singleflight_leader"] == 1
    assert snapshot["singleflight_follower"] == 9


async def test_different_keys_do_not_share_a_flight(flight: SingleFlight) -> None:
    calls: list[str] = []

    async def fn(key: str) -> str:
        calls.append(key)
        return key

    first, second = await asyncio.gather(
        flight.execute("a", lambda: fn("a")),
        flight.execute("b", lambda: fn("b")),
    )
    assert (first, second) == ("a", "b")
    assert sorted(calls) == ["a", "b"]


async def test_completed_result_replays_within_ttl(
    clock: ManualClock, flight: SingleFlight
) -> None:
    calls = 0

    async def fn() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await flight.execute("k", fn, replay_ttl=60) == 1
    assert await flight.execute("k", fn, replay_ttl=60) == 1
    assert calls == 1
    assert flight.metrics.snapshot()["singleflight_replay"] == 1

    clock.advance(61)
    assert await flight.execute("k", fn, replay_ttl=60) == 2
    assert calls == 2


async def test_replay_returns_the_identical_object(flight: SingleFlight) -> None:
    value = object()

    async def fn() -> object:
        return value

    assert await flight.execute("k", fn, replay_ttl=30) is value
    assert await flight.execute("k", fn, replay_ttl=30) is value


async def test_zero_ttl_never_replays(flight: SingleFlight) -> None:
    calls = 0

    async def fn() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await flight.execute("k", fn, replay_ttl=0) == 1
    assert await flight.execute("k", fn, replay_ttl=0) == 2
    assert calls == 2


async def test_cacheable_failure_is_replayed_then_retried(
    clock: ManualClock, flight: SingleFlight
) -> None:
    calls = 0
    error = AiInvalid("schema mismatch", stage=Stage.EXTRACTION)

    async def fn() -> str:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(AiInvalid):
        await flight.execute("k", fn, negative_ttl=10)
    with pytest.raises(AiInvalid):
        await flight.execute("k", fn, negative_ttl=10)
    assert calls == 1

    clock.advance(11)
    with pytest.raises(AiInvalid):
        await flight.execute("k", fn, negative_ttl=10)
    assert calls == 2


async def test_followers_see_the_very_same_failure(flight: SingleFlight) -> None:
    release = asyncio.Event()
    error = AiTimeout("vendor slow", stage=Stage.CHAT)

    async def fn() -> str:
        await release.wait()
        raise error

    tasks = [asyncio.create_task(flight.execute("k", fn)) for _ in range(3)]
    for _ in range(3):
        await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(result is error for result in results)


async def test_non_cacheable_failure_reruns_immediately(flight: SingleFlight) -> None:
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        raise AiTimeout("slow", stage=Stage.EVALUATION)

    for _ in range(2):
        with pytest.raises(AiTimeout):
            await flight.execute("k", fn, negative_ttl=60)
    assert calls == 2


async def test_cancelled_follower_leaves_the_flight_alone(flight: SingleFlight) -> None:
    release = asyncio.Event()
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "ok"

    leader = asyncio.create_task(flight.execute("k", fn))
    await asyncio.sleep(0)
    follower = asyncio.create_task(flight.execute("k", fn))
    await asyncio.sleep(0)

    follower.cancel()
    with pytest.raises(asyncio.CancelledError):
        await follower

    release.set()
    assert await leader == "ok"
    assert calls == 1


async def test_full_registry_fails_open(clock: ManualClock) -> None:
    flight = SingleFlight(clock=clock, max_entries=2)
    release = asyncio.Event()

    async def fn() -> str:
        await release.wait()
        return "v"

    tasks = [asyncio.create_task(flight.execute(f"k{index}", fn)) for index in range(3)]
    for _ in range(3):
        await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(*tasks) == ["v"] * 3
    snapshot = flight.metrics.snapshot()
    assert snapshot["singleflight_leader"] == 2
    assert snapshot["singleflight_direct"] == 1


async def test_expired_entries_are_evicted(clock: ManualClock) -> None:
    flight = SingleFlight(clock=clock, max_entries=2)

    async def fn() -> str:
        return "v"

    for index in range(3):
        await flight.execute(f"k{index}", fn, replay_ttl=1)
        clock.advance(2)

    assert flight.entry_count == 1


async def test_the_m1_passthrough_would_call_twice() -> None:
    """The red test behind this ticket: DirectAiResilience does not deduplicate."""
    direct = DirectAiResilience()
    calls = 0
    release = asyncio.Event()

    async def fn() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "x"

    tasks = [asyncio.create_task(direct.run(Stage.CHAT, "k", fn)) for _ in range(2)]
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(*tasks)

    assert calls == 2
