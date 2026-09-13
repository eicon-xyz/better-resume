"""Question locks: process-local by default, Redis for multi-instance runs (M6-T1).

Both implementations satisfy the same tiny interface (`acquire(session_id, question_no)`
as an async context manager) because `AnswerService` only knows that shape. The Redis one
adds an owner token (never delete somebody else's lock), a lease that is renewed while the
critical section runs, and a bounded wait with an explicit error.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import redis.asyncio as aioredis
import structlog

from ..ai_resilience import Clock, SystemClock

logger = structlog.get_logger("better_resume.interview_engine.locks")

#: Compare-and-delete: a lock whose lease expired and was taken over must not be deleted
#: by its previous owner. Three lines of Lua is the honest minimum here (single Redis).
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

#: Compare-and-extend, same token rule as the release path.
_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


class QuestionLockTimeout(RuntimeError):
    """Somebody else holds the lock longer than we are willing to wait."""


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


class QuestionLockRegistry:
    """One lock per (session, question); entries disappear once nobody holds them."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: str, question_no: str) -> AsyncIterator[None]:
        key = (session_id, question_no)
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry()
            self._entries[key] = entry
        entry.waiters += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.waiters -= 1
            if entry.waiters <= 0:
                self._entries.pop(key, None)

    def active_keys(self) -> list[tuple[str, str]]:
        return sorted(self._entries)

    async def aclose(self) -> None:
        """Nothing to release: kept so both implementations share one shutdown call."""
        return None


class RedisQuestionLockRegistry:
    """The multi-instance implementation of the same seam."""

    def __init__(
        self,
        redis_url: str,
        *,
        ttl_seconds: float = 30.0,
        wait_seconds: float = 10.0,
        poll_seconds: float = 0.05,
        clock: Clock | None = None,
    ) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl_ms = max(1, int(ttl_seconds * 1000))
        self._wait_seconds = wait_seconds
        self._poll_seconds = poll_seconds
        self._clock = clock or SystemClock()

    @staticmethod
    def key(session_id: str, question_no: str) -> str:
        return f"br:lock:question:{session_id}:{question_no}"

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: str, question_no: str) -> AsyncIterator[None]:
        key = self.key(session_id, question_no)
        token = secrets.token_urlsafe(16)
        deadline = self._clock.now() + self._wait_seconds

        while True:
            if await self._client.set(key, token, nx=True, px=self._ttl_ms):
                break
            if self._clock.now() >= deadline:
                raise QuestionLockTimeout(
                    f"question {question_no} is locked by another worker "
                    f"(waited {self._wait_seconds:g}s)"
                )
            await self._clock.sleep(self._poll_seconds)

        renew = asyncio.create_task(self._renew_loop(key, token), name="redis-lock-renew")
        try:
            yield
        finally:
            renew.cancel()
            with contextlib.suppress(BaseException):
                await renew
            await self._release(key, token)

    async def _renew_loop(self, key: str, token: str) -> None:
        while True:
            await self._clock.sleep(self._ttl_ms / 2000)
            renewed = await self._client.eval(_RENEW_LUA, 1, key, token, self._ttl_ms)
            if not renewed:
                # The lease was taken over: stop pretending we still hold it.
                logger.warning("question_lock_lost", key=key)
                return

    async def _release(self, key: str, token: str) -> None:
        with contextlib.suppress(Exception):
            await self._client.eval(_RELEASE_LUA, 1, key, token)

    async def ttl_ms(self, session_id: str, question_no: str) -> int:
        """Diagnostics for the kill-instance drill."""
        ttl = await self._client.pttl(self.key(session_id, question_no))
        return int(ttl)

    async def aclose(self) -> None:
        await self._client.aclose()
