"""ConversationStore seam: the single owner of session messages (§12.2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Message, SessionRef, UserId


@runtime_checkable
class ConversationStore(Protocol):
    async def append(self, session: SessionRef, msg: Message) -> int:
        """Append a message and return its sequence number."""
        ...

    async def history(
        self, session: SessionRef, *, before: int | None = None, limit: int = 50
    ) -> list[Message]:
        """Return the most recent messages, optionally before a sequence number."""
        ...

    async def require_owner(self, session: SessionRef, user_id: UserId) -> None:
        """Raise when the session does not belong to the user."""
        ...
