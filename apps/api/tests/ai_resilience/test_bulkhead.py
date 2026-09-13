"""M3-T5: bulkhead — bounded concurrency, bounded queue wait, no leaked slots."""

from __future__ import annotations

import asyncio

import pytest

from better_resume.ai_resilience import (
    AiOverloaded,
    Bulkhead,
    ManualClock,
    ResilienceMetrics,
    Stage,
)


def make_bulkhead(
    clock: ManualClock, *, limit: int = 2, wait: float = 2.0
) -> tuple[Bulkhead, ResilienceMetrics]:
    metrics = ResilienceMetrics()
    bulkhead = Bulkhead(
        stage=Stage.EVALUATION,
        max_concurrency=limit,
        queue_wait=wait,
        clock=clock,
        metrics=metrics,
    )
    return bulkhead, metrics


async def test_slots_are_bounded_and_waiters_are_admitted() -> None:
    clock = ManualClock()
    bulkhead, metrics = make_bulkhead(clock, limit=2)
    release = asyncio.Event()
    entered: list[str] = []

    async def work(name: str) -> None:
        async with bulkhead.slot():
            entered.append(name)
            await release.wait()

    running = [asyncio.create_task(work("a")), asyncio.create_task(work("b"))]
    for _ in range(3):
        await asyncio.sleep(0)
    queued = asyncio.create_task(work("c"))
    for _ in range(3):
        await asyncio.sleep(0)

    assert entered == ["a", "b"]
    assert bulkhead.in_flight == 2
    assert metrics.snapshot()["queued"] == 1

    release.set()
    await asyncio.gather(*running, queued)
    assert sorted(entered) == ["a", "b", "c"]
    assert bulkhead.in_flight == 0
    assert metrics.snapshot()["peak_in_flight"] == 2


async def test_queue_wait_budget_raises_overloaded() -> None:
    clock = ManualClock()
    bulkhead, metrics = make_bulkhead(clock, limit=1, wait=1.0)
    holder = asyncio.Event()

    async def hold() -> None:
        async with bulkhead.slot():
            await holder.wait()

    running = asyncio.create_task(hold())
    await asyncio.sleep(0)

    async def queued() -> None:
        async with bulkhead.slot():
            raise AssertionError("the queue should have timed out")

    waiter = asyncio.create_task(queued())
    for _ in range(3):
        await asyncio.sleep(0)
    assert waiter.done() is False  # still waiting for a slot

    clock.advance(1.1)
    with pytest.raises(AiOverloaded) as caught:
        await waiter

    assert caught.value.stage is Stage.EVALUATION
    assert caught.value.retryable is True
    assert "capacity" in str(caught.value)
    assert metrics.snapshot()["overflow_rejected"] == 1
    assert metrics.snapshot()["in_flight"] == 1

    holder.set()
    await running
    assert metrics.snapshot()["in_flight"] == 0


async def test_a_failing_body_still_releases_its_slot() -> None:
    clock = ManualClock()
    bulkhead, metrics = make_bulkhead(clock, limit=1)

    with pytest.raises(RuntimeError, match="boom"):
        async with bulkhead.slot():
            raise RuntimeError("boom")

    assert metrics.snapshot()["in_flight"] == 0
    async with bulkhead.slot():
        pass
    assert bulkhead.in_flight == 0
