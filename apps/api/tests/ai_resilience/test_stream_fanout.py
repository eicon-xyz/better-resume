"""M3-T3: streamed single flight — one upstream stream, many identical consumers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from better_resume.ai_resilience import ManualClock, SingleFlight


@pytest.fixture
def flight() -> SingleFlight:
    return SingleFlight(clock=ManualClock(), max_entries=16)


async def collect(stream: AsyncIterator[object]) -> list[object]:
    frames: list[object] = []
    async for frame in stream:
        frames.append(frame)
    return frames


def opener(source_factory: object) -> object:
    async def open_stream() -> AsyncIterator[object]:
        return source_factory()  # type: ignore[operator]

    return open_stream


async def test_three_consumers_share_one_upstream(flight: SingleFlight) -> None:
    subscriptions = 0

    async def source() -> AsyncIterator[str]:
        nonlocal subscriptions
        subscriptions += 1
        for index in range(5):
            await asyncio.sleep(0)
            yield f"f{index}"

    streams = await asyncio.gather(
        flight.execute("chat|s|h", opener(source), expect_stream=True),
        flight.execute("chat|s|h", opener(source), expect_stream=True),
        flight.execute("chat|s|h", opener(source), expect_stream=True),
    )

    results = await asyncio.gather(*(collect(stream) for stream in streams))
    assert subscriptions == 1
    assert results == [["f0", "f1", "f2", "f3", "f4"]] * 3
    assert flight.metrics.snapshot()["singleflight_follower"] == 2


async def test_late_subscriber_replays_from_the_first_frame(flight: SingleFlight) -> None:
    release = asyncio.Event()

    async def source() -> AsyncIterator[str]:
        yield "f0"
        await release.wait()
        yield "f1"
        yield "f2"

    leader = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    assert await anext(leader) == "f0"

    late = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    release.set()

    assert await collect(leader) == ["f1", "f2"]
    assert await collect(late) == ["f0", "f1", "f2"]


async def test_early_close_by_one_consumer_keeps_the_stream_alive(flight: SingleFlight) -> None:
    async def source() -> AsyncIterator[int]:
        for index in range(4):
            await asyncio.sleep(0)
            yield index

    leader = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    other = await flight.execute("chat|s|h", opener(source), expect_stream=True)

    assert await anext(leader) == 0
    await leader.aclose()  # type: ignore[attr-defined]

    assert await collect(other) == [0, 1, 2, 3]


async def test_last_consumer_leaving_cancels_the_producer(flight: SingleFlight) -> None:
    started = asyncio.Event()

    async def source() -> AsyncIterator[int]:
        started.set()
        while True:
            await asyncio.sleep(0)
            yield 1

    stream = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    assert await anext(stream) == 1
    broadcast = flight.active_stream("chat|s|h")
    assert broadcast is not None
    assert broadcast.consumer_count == 1

    await stream.aclose()  # type: ignore[attr-defined]
    for _ in range(3):
        await asyncio.sleep(0)

    assert broadcast.cancelled is True
    assert flight.entry_count == 0
    assert flight.metrics.snapshot()["singleflight_abandoned"] == 1


async def test_upstream_failure_reaches_every_consumer(flight: SingleFlight) -> None:
    async def source() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("vendor exploded")

    leader = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    other = await flight.execute("chat|s|h", opener(source), expect_stream=True)

    assert await anext(leader) == 1

    with pytest.raises(RuntimeError, match="vendor exploded"):
        await collect(leader)
    with pytest.raises(RuntimeError, match="vendor exploded"):
        await collect(other)


async def test_backpressure_stops_the_producer_at_the_buffer_limit(flight: SingleFlight) -> None:
    produced: list[int] = []

    async def source() -> AsyncIterator[int]:
        for index in range(50):
            produced.append(index)
            yield index

    stream = await flight.execute("chat|s|h", opener(source), expect_stream=True, stream_buffer=3)
    broadcast = flight.active_stream("chat|s|h")
    assert broadcast is not None

    for _ in range(30):
        await asyncio.sleep(0)

    assert broadcast.frame_count <= 3
    # The generator body appends before yielding, so the producer holds at most one
    # extra frame in hand while it waits for room.
    assert len(produced) <= 4

    assert await collect(stream) == list(range(50))


async def test_value_caller_on_a_stream_key_is_rejected(flight: SingleFlight) -> None:
    async def source() -> AsyncIterator[int]:
        yield 1

    async def value() -> str:
        return "v"

    stream = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    with pytest.raises(TypeError, match="bound to a live stream"):
        await flight.execute("chat|s|h", value)

    await stream.aclose()  # type: ignore[attr-defined]


async def test_stream_caller_on_a_value_key_is_rejected(flight: SingleFlight) -> None:
    async def value() -> str:
        return "v"

    with pytest.raises(TypeError, match="a stream was expected"):
        await flight.execute("eval|s|q", value, expect_stream=True)


async def test_finished_streams_are_never_replayed(flight: SingleFlight) -> None:
    subscriptions = 0

    async def source() -> AsyncIterator[str]:
        nonlocal subscriptions
        subscriptions += 1
        yield "x"

    first = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    assert await collect(first) == ["x"]
    for _ in range(3):
        await asyncio.sleep(0)

    assert flight.entry_count == 0
    second = await flight.execute("chat|s|h", opener(source), expect_stream=True)
    assert await collect(second) == ["x"]
    assert subscriptions == 2
