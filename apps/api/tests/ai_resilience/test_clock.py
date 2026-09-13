"""M3-T1: the clock seam — real time in production, manual time in tests."""

from __future__ import annotations

import asyncio

import pytest

from better_resume.ai_resilience import ManualClock, SystemClock


def test_system_clock_is_monotonic_and_sleeps() -> None:
    clock = SystemClock()
    first = clock.now()
    assert clock.now() >= first

    async def run() -> None:
        await clock.sleep(0)

    asyncio.run(run())


@pytest.mark.asyncio
async def test_manual_clock_does_not_wait_in_real_time() -> None:
    clock = ManualClock()
    assert clock.now() == 0.0

    async def wait() -> None:
        await clock.sleep(30.0)

    task = asyncio.create_task(wait())
    await asyncio.sleep(0)
    assert task.done() is False

    clock.advance(29.9)
    await asyncio.sleep(0)
    assert task.done() is False

    clock.advance(0.2)
    await asyncio.sleep(0)
    assert task.done() is True
    assert clock.now() == pytest.approx(30.1)


@pytest.mark.asyncio
async def test_manual_clock_wakes_only_due_waiters_and_sleep_zero_is_immediate() -> None:
    clock = ManualClock(start=100.0)
    fired: list[str] = []

    async def wait(name: str, seconds: float) -> None:
        await clock.sleep(seconds)
        fired.append(name)

    tasks = [asyncio.create_task(wait("short", 1.0)), asyncio.create_task(wait("long", 10.0))]
    await asyncio.sleep(0)
    clock.advance(1.0)
    await asyncio.sleep(0)
    assert fired == ["short"]

    clock.advance(9.0)
    await asyncio.sleep(0)
    assert fired == ["short", "long"]

    await clock.sleep(0)
    await asyncio.gather(*tasks)
