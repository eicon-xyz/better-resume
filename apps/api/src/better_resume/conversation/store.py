"""Postgres implementation of ConversationStore plus the conversation lifecycle.

Sequence allocation is transactional (row lock on the conversation + unique index backstop);
no Redis Lua allocator is needed (D03 keeps the storage layer to Postgres + Redis).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import ConversationConflictError, ConversationNotFoundError
from .models import Conversation, Message, SessionKind, SessionRef, StoredMessage, UserId
from .orm import ConversationMessageRow, ConversationRow


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class SqlConversationStore:
    """Per-request store bound to one AsyncSession; callers own the transaction."""

    def __init__(self, session: AsyncSession, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._session = session
        self._clock = clock

    # ---- conversation lifecycle -------------------------------------------------

    async def create(
        self,
        *,
        kind: SessionKind,
        user_id: UserId,
        title: str = "",
        model_ref: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Conversation:
        now = self._clock()
        row = ConversationRow(
            id=str(uuid.uuid4()),
            kind=kind,
            user_id=user_id,
            title=title[:200],
            model_ref=model_ref,
            message_count=0,
            meta=meta or {},
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_conversation(row)

    async def list_for_user(
        self, user_id: UserId, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        stmt = (
            select(ConversationRow)
            .where(ConversationRow.user_id == user_id)
            .order_by(ConversationRow.updated_at.desc(), ConversationRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_conversation(row) for row in rows]

    async def require_owner(self, session: SessionRef, user_id: UserId) -> None:
        row = await self._fetch(session)
        if row.user_id != user_id:
            raise ConversationNotFoundError(f"conversation {session.session_id} not found")

    async def update_title(self, session: SessionRef, user_id: UserId, title: str) -> None:
        row = await self._fetch(session, for_update=True)
        if row.user_id != user_id:
            raise ConversationNotFoundError(f"conversation {session.session_id} not found")
        row.title = title[:200]
        row.updated_at = self._clock()
        await self._session.flush()

    async def delete(self, session: SessionRef, user_id: UserId) -> None:
        row = await self._fetch(session)
        if row.user_id != user_id:
            raise ConversationNotFoundError(f"conversation {session.session_id} not found")
        await self._session.delete(row)
        await self._session.flush()

    # ---- messages ---------------------------------------------------------------

    async def append(
        self,
        session: SessionRef,
        msg: Message,
        *,
        client_message_id: str | None = None,
        token_count: int | None = None,
        error_message: str | None = None,
    ) -> int:
        """Append a message and return its seq; re-sending the same client id is a no-op."""
        row = await self._fetch(session, for_update=True)

        if client_message_id is not None:
            existing = await self._session.execute(
                select(ConversationMessageRow.seq).where(
                    ConversationMessageRow.conversation_id == row.id,
                    ConversationMessageRow.client_message_id == client_message_id,
                )
            )
            replayed = existing.scalar_one_or_none()
            if replayed is not None:
                return replayed

        seq = row.message_count + 1
        now = self._clock()
        self._session.add(
            ConversationMessageRow(
                id=str(uuid.uuid4()),
                conversation_id=row.id,
                seq=seq,
                role=msg.role,
                content=msg.content,
                reasoning=msg.reasoning,
                token_count=token_count,
                error_message=error_message,
                client_message_id=client_message_id,
                meta=msg.meta,
                created_at=now,
            )
        )
        row.message_count = seq
        row.updated_at = now

        try:
            await self._session.flush()
        except IntegrityError as exc:  # backstop: seq must stay unique per conversation
            raise ConversationConflictError(
                f"sequence conflict while appending to {session.session_id}"
            ) from exc
        return seq

    async def history(
        self, session: SessionRef, *, before: int | None = None, limit: int = 50
    ) -> list[StoredMessage]:
        await self._fetch(session)

        stmt = select(ConversationMessageRow).where(
            ConversationMessageRow.conversation_id == session.session_id
        )
        if before is not None:
            stmt = stmt.where(ConversationMessageRow.seq < before)
        stmt = stmt.order_by(ConversationMessageRow.seq.desc()).limit(limit)

        rows: Sequence[ConversationMessageRow] = (await self._session.execute(stmt)).scalars().all()
        return [_to_stored(row) for row in reversed(rows)]

    # ---- internals --------------------------------------------------------------

    async def _fetch(self, session: SessionRef, *, for_update: bool = False) -> ConversationRow:
        stmt = select(ConversationRow).where(
            ConversationRow.id == session.session_id, ConversationRow.kind == session.kind
        )
        if for_update:
            stmt = stmt.with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ConversationNotFoundError(f"conversation {session.session_id} not found")
        return row


def _to_conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=row.id,
        kind=row.kind,  # type: ignore[arg-type]
        user_id=row.user_id,
        title=row.title,
        model_ref=row.model_ref,
        message_count=row.message_count,
        meta=row.meta,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_stored(row: ConversationMessageRow) -> StoredMessage:
    return StoredMessage(
        id=row.id,
        seq=row.seq,
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        reasoning=row.reasoning,
        token_count=row.token_count,
        error_message=row.error_message,
        meta=row.meta,
        created_at=row.created_at,
    )
