"""Deadlines on the injected clock, so tests advance time instead of sleeping.

asyncio.wait_for / asyncio.timeout are deliberately not used: they read the event loop
clock, which would make timeout behaviour impossible to drive from ManualClock (and would
force real sleeps into every timeout test).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

from .clock import Clock
from .errors import AiTimeout
from .models import Stage


async def run_with_deadline[T](awaitable: Awaitable[T], *, seconds: float, clock: Clock) -> T:
    """Await the given awaitable, but give up once the clock has moved on."""
    task: asyncio.Future[T] = asyncio.ensure_future(awaitable)
    timer: asyncio.Task[None] = asyncio.create_task(clock.sleep(max(0.0, seconds)))
    try:
        await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            if task.cancelled():
                raise asyncio.CancelledError()
            return task.result()
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
        raise TimeoutError(f"deadline of {seconds:g}s exceeded")
    except BaseException:
        if not task.done():
            task.cancel()
        raise
    finally:
        timer.cancel()
        with contextlib.suppress(BaseException):
            await timer


async def with_timeout[T](
    stage: Stage,
    timeout: float,  # noqa: ASYNC109 - the deadline is measured on the injected clock
    awaitable: Awaitable[T],
    *,
    clock: Clock,
) -> T:
    try:
        return await run_with_deadline(awaitable, seconds=timeout, clock=clock)
    except TimeoutError as exc:
        raise AiTimeout(f"stage {stage.value} exceeded {timeout:g}s", stage=stage) from exc


async def wrap_stream_timeout[T](
    stream: AsyncIterator[T],
    *,
    stage: Stage,
    timeout: float,  # noqa: ASYNC109 - one budget for the whole stream, on the injected clock
    clock: Clock,
    on_timeout: Callable[[], None] | None = None,
) -> AsyncIterator[T]:
    """Apply one budget to the whole stream (open to last frame), not per frame."""
    deadline = clock.now() + timeout
    while True:
        remaining = deadline - clock.now()
        if remaining <= 0:
            await aclose_quietly(stream)
            if on_timeout is not None:
                on_timeout()
            raise AiTimeout(f"stage {stage.value} stream exceeded {timeout:g}s", stage=stage)
        try:
            frame = await run_with_deadline(anext(stream), seconds=remaining, clock=clock)
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            await aclose_quietly(stream)
            if on_timeout is not None:
                on_timeout()
            raise AiTimeout(
                f"stage {stage.value} stream exceeded {timeout:g}s", stage=stage
            ) from exc
        yield frame


async def aclose_quietly(source: object) -> None:
    aclose = getattr(source, "aclose", None)
    if aclose is None:
        return
    with contextlib.suppress(BaseException):
        await aclose()
