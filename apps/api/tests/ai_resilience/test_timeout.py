"""M3-T5: deadlines driven by the manual clock (no real sleeping in tests)."""

from __future__ import annotations

import asyncio

import pytest

from better_resume.ai_resilience import AiTimeout, ManualClock, Stage
from better_resume.ai_resilience.timeout import run_with_deadline, with_timeout, wrap_stream_timeout


async def test_value_timeout_fires_when_the_clock_advances() -> None:
    clock = ManualClock()
    started = asyncio.Event()
    cancelled = False

    async def slow() -> str:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    task = asyncio.create_task(with_timeout(Stage.EVALUATION, 20.0, slow(), clock=clock))
    for _ in range(5):  # let the wrapper schedule the inner task
        await asyncio.sleep(0)
    assert started.is_set()
    assert task.done() is False

    clock.advance(20.1)
    with pytest.raises(AiTimeout) as caught:
        await task

    assert caught.value.stage is Stage.EVALUATION
    assert caught.value.retryable is True
    assert cancelled is True  # the upstream task was cancelled, not orphaned


async def test_value_completes_inside_the_budget() -> None:
    clock = ManualClock()

    async def quick() -> int:
        return 42

    assert await with_timeout(Stage.CHAT, 180.0, quick(), clock=clock) == 42


async def test_deadline_propagates_upstream_errors() -> None:
    clock = ManualClock()

    async def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await run_with_deadline(boom(), seconds=5.0, clock=clock)


async def test_external_cancellation_reaches_the_inner_task() -> None:
    clock = ManualClock()
    cancelled = asyncio.Event()

    async def slow() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(run_with_deadline(slow(), seconds=100.0, clock=clock))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


async def test_stream_within_budget_is_not_killed() -> None:
    clock = ManualClock()

    async def source() -> object:
        yield "a"
        clock.advance(5.0)  # time passes, but the budget is 30s
        yield "b"

    frames = [
        frame
        async for frame in wrap_stream_timeout(
            source(), stage=Stage.CHAT, timeout=30.0, clock=clock
        )
    ]
    assert frames == ["a", "b"]


async def test_stream_timeout_cancels_the_producer() -> None:
    clock = ManualClock()
    cancelled = False

    async def source() -> object:
        nonlocal cancelled
        try:
            yield 1
            await asyncio.Event().wait()
        finally:
            cancelled = True

    stream = wrap_stream_timeout(source(), stage=Stage.CHAT, timeout=30.0, clock=clock)
    assert await anext(stream) == 1

    clock.advance(30.1)
    with pytest.raises(AiTimeout) as caught:
        await anext(stream)

    assert caught.value.stage is Stage.CHAT
    assert cancelled is True


async def test_stream_timeout_before_the_first_frame() -> None:
    clock = ManualClock()

    async def source() -> object:
        await asyncio.Event().wait()
        yield 1

    stream = wrap_stream_timeout(source(), stage=Stage.CHAT, timeout=1.0, clock=clock)
    task = asyncio.create_task(anext(stream))
    # ManualClock only wakes sleepers that already registered their deadline, so let the
    # wrapper (and its timer task) start before moving time forward.
    for _ in range(5):
        await asyncio.sleep(0)

    clock.advance(1.0)
    with pytest.raises(AiTimeout):
        await task
