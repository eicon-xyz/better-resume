"""WS handshake tickets (D11): interface only in M0, implementation lands with the WS transport."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Principal


@runtime_checkable
class WsTicketStore(Protocol):
    """One-shot ticket: issued on an authed HTTP call, consumed by the WS handshake."""

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str: ...

    async def consume(self, ticket: str) -> Principal | None: ...


class UnimplementedWsTicketStore:
    """Explicit placeholder: fails loudly instead of pretending to work."""

    async def issue(self, principal: Principal, *, ttl_seconds: int) -> str:
        raise NotImplementedError("WS ticket issuing lands with the WS transport (M1+)")

    async def consume(self, ticket: str) -> Principal | None:
        raise NotImplementedError("WS ticket consuming lands with the WS transport (M1+)")
