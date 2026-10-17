"""the bounded wait primitive: one loop, always on the injected clock."""

from __future__ import annotations

import asyncio

import pytest

from better_resume.ai_resilience import ManualClock, wait_until

from ..support import settle


async def test_wait_returns_as_soon_as_the_condition_holds() -> None:
    clock = ManualClock()
    released = False

    async def release() -> None:
        nonlocal released
        await clock.sleep(0.5)
        released = True

    releaser = asyncio.create_task(release())
    waiter = asyncio.create_task(
        wait_until(lambda: released, clock=clock, timeout=5.0, interval=0.1)
    )
    await settle(2)  # both tasks are parked on the clock
    clock.advance(0.5)
    await settle(2)

    await waiter
    await releaser


async def test_wait_parks_on_the_clock_instead_of_spinning() -> None:
    """P04's shape: the wait must register a sleeper, so one advance settles it and a
    test never has to guess how many loop turns it takes."""
    clock = ManualClock()
    waiter = asyncio.create_task(wait_until(lambda: False, clock=clock, timeout=1.0, interval=0.1))
    await settle()

    assert clock.pending_waiters == 1
    clock.advance(1.0)
    with pytest.raises(TimeoutError, match="waited 1s"):
        await waiter
    assert clock.pending_waiters == 0


async def test_wait_polls_a_bounded_number_of_times() -> None:
    clock = ManualClock()
    polls = 0

    def never() -> bool:
        nonlocal polls
        polls += 1
        return False

    waiter = asyncio.create_task(wait_until(never, clock=clock, timeout=1.0, interval=0.25))
    await settle()
    clock.advance(1.0)

    with pytest.raises(TimeoutError):
        await waiter
    assert polls <= 3  # a sleeper between polls, not a spin


async def test_an_async_condition_is_awaited() -> None:
    seen = 0

    async def condition() -> bool:
        nonlocal seen
        seen += 1
        return seen >= 3

    await wait_until(condition, timeout=1.0, interval=0.001)
    assert seen == 3


async def test_a_non_positive_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="interval"):
        await wait_until(lambda: True, timeout=1.0, interval=0.0)
