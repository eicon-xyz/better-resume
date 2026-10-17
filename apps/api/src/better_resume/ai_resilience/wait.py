"""Bounded waits on the injected clock: one loop, no busy-spin, no real-time assumption."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from .clock import Clock, SystemClock


async def wait_until(
    condition: Callable[[], bool | Awaitable[bool]],
    *,
    timeout: float,  # noqa: ASYNC109 - the budget is measured on the injected clock
    clock: Clock | None = None,
    interval: float = 0.01,
    description: str = "condition",
) -> None:
    """Wait for `condition` to hold, bounded by the injected clock.

    Every poll registers a sleeper on the clock instead of spinning through `sleep(0)`: fake
    time can drive the wait to completion, a test can observe it parked, and a zero interval
    (the shape that never notices an advance) is refused. Real I/O waits pass no clock and
    get the system one; the interval is the only real-time cost, and the same budget bounds it.
    """
    if interval <= 0:
        raise ValueError("wait_until needs a positive interval: a zero interval would spin")
    active_clock = clock or SystemClock()
    deadline = active_clock.now() + timeout
    while True:
        if await _holds(condition):
            return
        remaining = deadline - active_clock.now()
        if remaining <= 0:
            raise TimeoutError(f"waited {timeout:g}s on the injected clock for {description}")
        await active_clock.sleep(min(interval, remaining))


async def _holds(condition: Callable[[], bool | Awaitable[bool]]) -> bool:
    outcome = condition()
    if inspect.isawaitable(outcome):
        return bool(await outcome)
    return bool(outcome)
