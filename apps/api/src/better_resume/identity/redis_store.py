"""Redis-backed session store (D11: HttpOnly cookie session, 30-day sliding TTL)."""

from __future__ import annotations

import time
from collections.abc import Callable

import redis.asyncio as redis

from .models import Principal, SessionRecord
from .store import new_session_id


class RedisSessionStore:
    """Sessions live under `<prefix><session_id>` as JSON with a server-side TTL."""

    def __init__(
        self,
        redis_url: str,
        *,
        client: redis.Redis | None = None,
        key_prefix: str = "session:",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = client or redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix
        self._clock = clock

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    async def _write(self, record: SessionRecord, *, ttl_seconds: int) -> None:
        await self._redis.set(
            self._key(record.session_id), record.model_dump_json(), ex=ttl_seconds
        )

    async def create(self, principal: Principal, *, ttl_seconds: int) -> SessionRecord:
        now = self._clock()
        record = SessionRecord(
            session_id=new_session_id(),
            principal=principal,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        await self._write(record, ttl_seconds=ttl_seconds)
        return record

    async def get(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        return SessionRecord.model_validate_json(raw)

    async def touch(self, session_id: str, *, ttl_seconds: int) -> SessionRecord | None:
        record = await self.get(session_id)
        if record is None:
            return None
        refreshed = record.model_copy(update={"expires_at": self._clock() + ttl_seconds})
        await self._write(refreshed, ttl_seconds=ttl_seconds)
        return refreshed

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def aclose(self) -> None:
        await self._redis.aclose()
