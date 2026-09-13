"""In-memory session store: used by tests and by clock-injected expiry tests."""

from __future__ import annotations

import time
from collections.abc import Callable

from .models import Principal, SessionRecord
from .store import new_session_id


class InMemorySessionStore:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._sessions: dict[str, SessionRecord] = {}

    async def create(self, principal: Principal, *, ttl_seconds: int) -> SessionRecord:
        now = self._clock()
        record = SessionRecord(
            session_id=new_session_id(),
            principal=principal,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        self._sessions[record.session_id] = record
        return record

    async def get(self, session_id: str) -> SessionRecord | None:
        record = self._sessions.get(session_id)
        if record is None:
            return None
        if record.expires_at <= self._clock():
            self._sessions.pop(session_id, None)
            return None
        return record

    async def touch(self, session_id: str, *, ttl_seconds: int) -> SessionRecord | None:
        record = await self.get(session_id)
        if record is None:
            return None
        refreshed = record.model_copy(update={"expires_at": self._clock() + ttl_seconds})
        self._sessions[session_id] = refreshed
        return refreshed

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def aclose(self) -> None:
        self._sessions.clear()
