"""Session store seam: Redis in production, in-memory for tests."""

from __future__ import annotations

import secrets
from typing import Protocol, runtime_checkable

from .models import Principal, SessionRecord


def new_session_id() -> str:
    """Opaque, high-entropy session id (never derived from user data)."""
    return secrets.token_urlsafe(32)


@runtime_checkable
class SessionStore(Protocol):
    """Minimal session persistence contract; TTL is sliding on read (`touch`)."""

    async def create(self, principal: Principal, *, ttl_seconds: int) -> SessionRecord: ...

    async def get(self, session_id: str) -> SessionRecord | None: ...

    async def touch(self, session_id: str, *, ttl_seconds: int) -> SessionRecord | None: ...

    async def delete(self, session_id: str) -> None: ...

    async def aclose(self) -> None: ...
