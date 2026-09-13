"""Explicit M0 placeholder; the Postgres+JSONB store lands with M1."""

from __future__ import annotations

from .models import Message, SessionRef, UserId

_REASON = "ConversationStore is implemented in M1 (Postgres + JSONB)."


class UnimplementedConversationStore:
    async def append(self, session: SessionRef, msg: Message) -> int:
        raise NotImplementedError(_REASON)

    async def history(
        self, session: SessionRef, *, before: int | None = None, limit: int = 50
    ) -> list[Message]:
        raise NotImplementedError(_REASON)

    async def require_owner(self, session: SessionRef, user_id: UserId) -> None:
        raise NotImplementedError(_REASON)
