"""WS handshake tickets (D11): issued over authed HTTP, consumed once by the WS handshake."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

import redis.asyncio as aioredis

from .models import Principal

#: Atomic take-and-delete: two sockets racing with the same ticket cannot both win.
#: (Redis 6.0 has no GETDEL, so a two-line script keeps the one-shot guarantee.)
_CONSUME_LUA = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


@runtime_checkable
class WsTicketStore(Protocol):
    """One-shot ticket: issued on an authed HTTP call, consumed by the WS handshake."""

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str: ...

    async def consume(self, ticket: str) -> Principal | None: ...

    async def aclose(self) -> None: ...


def new_ticket() -> str:
    return secrets.token_urlsafe(32)


class InMemoryWsTicketStore:
    """Tests and single-process runs; expiry uses a monotonic clock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._tickets: dict[str, tuple[Principal, float]] = {}

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str:
        ticket = new_ticket()
        self._tickets[ticket] = (principal, self._clock() + ttl_seconds)
        return ticket

    async def consume(self, ticket: str) -> Principal | None:
        entry = self._tickets.pop(ticket, None)  # pop first: one shot even when expired
        if entry is None:
            return None
        principal, expires_at = entry
        if expires_at <= self._clock():
            return None
        return principal

    async def aclose(self) -> None:
        self._tickets.clear()


class RedisWsTicketStore:
    def __init__(self, redis_url: str) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _key(ticket: str) -> str:
        return f"br:ws_ticket:{ticket}"

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str:
        ticket = new_ticket()
        await self._client.set(
            self._key(ticket), json.dumps(principal.model_dump()), ex=ttl_seconds
        )
        return ticket

    async def consume(self, ticket: str) -> Principal | None:
        raw = await self._client.eval(_CONSUME_LUA, 1, self._key(ticket))
        if not raw:
            return None
        try:
            return Principal.model_validate(json.loads(raw))
        except (TypeError, ValueError):
            return None

    async def aclose(self) -> None:
        await self._client.aclose()


class UnimplementedWsTicketStore:
    """Explicit placeholder: fails loudly instead of pretending to work."""

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str:
        raise NotImplementedError("WS ticket issuing is not wired in this build")

    async def consume(self, ticket: str) -> Principal | None:
        raise NotImplementedError("WS ticket consuming is not wired in this build")

    async def aclose(self) -> None:
        return None
