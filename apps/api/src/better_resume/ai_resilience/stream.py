"""Fan-out for streamed AI calls: one upstream stream, many consumers (§4.1.5 spirit).

A chat stream cannot be deduplicated by handing the same async generator to two callers —
the second consumer gets "already running" errors. So a single-flight stream keeps one
producer task plus a shared frame buffer; every consumer walks the buffer with its own
cursor, late subscribers replay from the first frame, and the producer is cancelled as
soon as the last consumer detaches. Frames are kept for the whole flight so late joiners
stay byte-identical with the leader (chat replies are bounded by max_tokens).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable

import structlog

from .metrics import ResilienceMetrics

logger = structlog.get_logger("better_resume.ai_resilience.stream")


class _Consumer:
    __slots__ = ("index", "wakeup")

    def __init__(self) -> None:
        self.index = 0
        self.wakeup = asyncio.Event()


class StreamBroadcast[T]:
    """A replayable window over one upstream stream."""

    def __init__(
        self,
        *,
        name: str,
        max_buffered: int = 1024,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._name = name
        self._max_buffered = max(1, max_buffered)
        self._metrics = metrics or ResilienceMetrics()
        self._frames: list[T] = []
        self._consumers: list[_Consumer] = []
        self._error: BaseException | None = None
        self._done = False
        self._cancelled = False
        self._task: asyncio.Task[None] | None = None
        self._on_finish: Callable[[], None] | None = None
        # Producers wait on this when the slowest consumer is too far behind.
        self._progress = asyncio.Event()

    # ---- observable state (stats endpoint + tests) ------------------------------

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def consumer_count(self) -> int:
        return len(self._consumers)

    @property
    def finished(self) -> bool:
        return self._done

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def error(self) -> BaseException | None:
        return self._error

    # ---- lifecycle --------------------------------------------------------------

    def start(
        self,
        source: AsyncIterator[T],
        *,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self._on_finish = on_finish
        self._task = asyncio.create_task(
            self._produce(source), name=f"stream-broadcast:{self._name}"
        )

    def subscribe(self) -> AsyncIterator[T]:
        consumer = _Consumer()
        self._consumers.append(consumer)
        return self._iterate(consumer)

    async def aclose(self) -> None:
        """Shutdown path: stop the producer and let both parties settle."""
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        with contextlib.suppress(BaseException):
            await self._task

    # ---- producer ---------------------------------------------------------------

    async def _produce(self, source: AsyncIterator[T]) -> None:
        try:
            async for frame in source:
                await self._wait_for_room()
                self._frames.append(frame)
                self._wake_all()
        except asyncio.CancelledError:
            self._cancelled = True
            self._done = True
            self._wake_all()
            raise
        except BaseException as exc:  # noqa: BLE001 - waiters must see the failure
            self._error = exc
            self._done = True
            self._wake_all()
        else:
            self._done = True
            self._wake_all()
        finally:
            if self._on_finish is not None:
                self._on_finish()

    async def _wait_for_room(self) -> None:
        while self._consumers and self._lag() >= self._max_buffered:
            self._progress.clear()
            if not self._consumers or self._lag() < self._max_buffered:
                return
            await self._progress.wait()

    def _lag(self) -> int:
        if not self._consumers:
            return 0
        slowest = min(consumer.index for consumer in self._consumers)
        return len(self._frames) - slowest

    def _wake_all(self) -> None:
        self._progress.set()
        for consumer in self._consumers:
            consumer.wakeup.set()

    # ---- consumer ---------------------------------------------------------------

    async def _iterate(self, consumer: _Consumer) -> AsyncIterator[T]:
        try:
            while True:
                if consumer.index < len(self._frames):
                    frame = self._frames[consumer.index]
                    consumer.index += 1
                    self._progress.set()
                    yield frame
                    continue
                if self._error is not None:
                    raise self._error
                if self._done:
                    return
                consumer.wakeup.clear()
                # Re-check after clearing: a publish between check and wait must not be lost.
                if consumer.index < len(self._frames) or self._error is not None or self._done:
                    continue
                await consumer.wakeup.wait()
        finally:
            self._detach(consumer)

    def _detach(self, consumer: _Consumer) -> None:
        if consumer in self._consumers:
            self._consumers.remove(consumer)
        self._progress.set()
        producer_running = self._task is not None and not self._task.done()
        if not self._consumers and not self._done and producer_running:
            # Nobody is listening any more: stop paying for the model call.
            self._metrics.singleflight_abandoned += 1
            self._task.cancel()
