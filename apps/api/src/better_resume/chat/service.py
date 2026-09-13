"""Chat orchestration: history in, stream out, both messages persisted.

Mirrors the old ConversationStreamingSupport guarantee: even a failed turn leaves an
assistant message behind so history stays complete (§7.2).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..ai_resilience import AiResilience, Stage
from ..conversation import (
    Conversation,
    Message,
    SessionRef,
    SqlConversationStore,
    StoredMessage,
    UserId,
)
from ..llm_gateway import (
    ChatRequest,
    ContentDelta,
    Done,
    FailureKind,
    LlmError,
    LlmGateway,
    ReasoningDelta,
    TokenUsage,
    VendorMeta,
)
from ..llm_gateway import (
    Message as GatewayMessage,
)
from .models import ChatErrorEvent, ChatStreamEvent

logger = structlog.get_logger("better_resume.chat")

CANCELLED_ERROR = "cancelled"


def build_resilience_key(session_id: str, content: str) -> str:
    """key = stage|sessionId|sha256(payload), per §12.2 (chat has no question number)."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"chat|{session_id}|{digest}"


class ChatService:
    """One instance per request; it owns the DB session it opens for the whole turn."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        resilience: AiResilience,
        history_limit: int = 20,
    ) -> None:
        self._session_factory = session_factory
        self._resilience = resilience
        self._history_limit = history_limit

    async def stream_reply(
        self,
        *,
        session: SessionRef,
        user_id: UserId,
        content: str,
        gateway: LlmGateway,
        model_ref: str | None = None,
        client_message_id: str | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        async with self._session_factory() as db:
            store = SqlConversationStore(db)
            conversation = await self._load(store, session, user_id)

            if client_message_id and await self._is_duplicate(store, session, client_message_id):
                logger.info("chat_duplicate_request", session_id=session.session_id)
                yield ChatErrorEvent(
                    message="duplicate client_message_id: request ignored",
                    kind="duplicate_request",
                )
                return

            history = await store.history(session, limit=self._history_limit)
            await store.append(
                session, Message(role="user", content=content), client_message_id=client_message_id
            )
            await db.commit()

            request = self._build_request(conversation, history, content, model_ref)
            answer = ""
            reasoning = ""
            usage: TokenUsage | None = None
            finish_reason: str | None = None
            failure: LlmError | None = None

            persisted = False
            try:
                try:
                    stream = await self._resilience.run(
                        Stage.CHAT,
                        build_resilience_key(session.session_id, content),
                        lambda: _open_stream(gateway, request),
                    )
                    async for event in stream:
                        if isinstance(event, ContentDelta):
                            answer += event.text
                        elif isinstance(event, ReasoningDelta):
                            reasoning += event.text
                        elif isinstance(event, VendorMeta):
                            usage = _usage_from(event)
                        elif isinstance(event, Done):
                            finish_reason = event.finish_reason
                        yield event
                except LlmError as exc:
                    failure = exc
                    logger.warning(
                        "chat_stream_failed", session_id=session.session_id, error=str(exc)
                    )

                await self._persist(
                    session,
                    answer,
                    reasoning,
                    usage,
                    finish_reason,
                    error_message=_error_text(failure),
                )
                persisted = True
            finally:
                # Client hung up (task cancellation) or the consumer closed us early
                # (GeneratorExit): still land the partial answer so history stays complete.
                if not persisted:
                    await self._persist_aborted(session, answer, reasoning, usage, finish_reason)
                    logger.info("chat_stream_cancelled", session_id=session.session_id)

            if failure is not None:
                yield ChatErrorEvent(message=str(failure), kind=failure.kind.value)

    async def _persist_aborted(
        self,
        session: SessionRef,
        answer: str,
        reasoning: str,
        usage: TokenUsage | None,
        finish_reason: str | None,
    ) -> None:
        write = asyncio.create_task(
            self._persist(
                session, answer, reasoning, usage, finish_reason, error_message=CANCELLED_ERROR
            )
        )
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            await write  # unwinding, but the write itself must still land

    # ---- internals --------------------------------------------------------------

    async def _load(
        self, store: SqlConversationStore, session: SessionRef, user_id: UserId
    ) -> Conversation:
        await store.require_owner(session, user_id)
        conversations = await store.list_for_user(user_id, limit=200)
        for conversation in conversations:
            if conversation.id == session.session_id:
                return conversation
        # require_owner passed but the row was filtered out: treat as missing.
        from ..conversation import ConversationNotFoundError

        raise ConversationNotFoundError(session.session_id)

    async def _is_duplicate(
        self, store: SqlConversationStore, session: SessionRef, client_message_id: str
    ) -> bool:
        return await store.has_client_message_id(session, client_message_id)

    def _build_request(
        self,
        conversation: Conversation,
        history: list[StoredMessage],
        content: str,
        model_ref: str | None,
    ) -> ChatRequest:
        messages = [
            GatewayMessage(role=message.role, content=message.content)
            for message in history
            if message.role in ("user", "assistant") and message.content
        ]
        messages.append(GatewayMessage(role="user", content=content))
        return ChatRequest(
            messages=messages,
            model_ref=model_ref or conversation.model_ref,
            vendor_ctx=None,
        )

    async def _persist(
        self,
        session: SessionRef,
        answer: str,
        reasoning: str,
        usage: TokenUsage | None,
        finish_reason: str | None,
        *,
        error_message: str | None,
    ) -> None:
        async with self._session_factory() as db:
            store = SqlConversationStore(db)
            await store.append(
                session,
                Message(
                    role="assistant",
                    content=answer,
                    reasoning=reasoning or None,
                    meta={
                        "finish_reason": finish_reason,
                        "usage": usage.model_dump() if usage else None,
                    },
                ),
                token_count=usage.total_tokens if usage else None,
                error_message=error_message,
            )
            await db.commit()


async def _open_stream(gateway: LlmGateway, request: ChatRequest) -> AsyncIterator[object]:
    """Handed to AiResilience.run: opening the stream is the unit that gets deduplicated."""
    return gateway.stream(request)


def _usage_from(event: VendorMeta) -> TokenUsage | None:
    raw = event.extra.get("usage") or {}
    if not raw:
        return None
    return TokenUsage(
        prompt_tokens=raw.get("prompt_tokens"),
        completion_tokens=raw.get("completion_tokens"),
        total_tokens=raw.get("total_tokens"),
    )


def _error_text(failure: LlmError | None) -> str | None:
    if failure is None:
        return None
    if failure.kind is FailureKind.RETRYABLE:
        return f"upstream unavailable: {failure}"
    return str(failure)
