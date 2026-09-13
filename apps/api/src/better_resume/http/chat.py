"""Chat HTTP surface: session lifecycle, history paging and the SSE stream (§7.2)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from ..chat import (
    ChatErrorEvent,
    ChatMessageView,
    ChatService,
    ChatSessionCreateRequest,
    ChatSessionView,
    SessionUpdateRequest,
    StreamRequest,
)
from ..conversation import Conversation, SessionRef, SqlConversationStore, StoredMessage
from ..identity import Principal, current_principal
from ..llm_gateway import (
    ContentDelta,
    Done,
    LlmConfigError,
    ModelRegistry,
    ReasoningDelta,
    VendorMeta,
)

logger = structlog.get_logger("better_resume.chat.http")

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # nginx must not buffer the stream
}


def _ref(session_id: str) -> SessionRef:
    return SessionRef(kind="chat", session_id=session_id)


def _session_view(conversation: Conversation) -> ChatSessionView:
    return ChatSessionView(
        id=conversation.id,
        kind=conversation.kind,
        title=conversation.title,
        model_ref=conversation.model_ref,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_view(message: StoredMessage) -> ChatMessageView:
    return ChatMessageView(
        id=message.id,
        seq=message.seq,
        role=message.role,
        client_message_id=message.client_message_id,
        content=message.content,
        reasoning=message.reasoning,
        token_count=message.token_count,
        error_message=message.error_message,
        created_at=message.created_at,
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreateRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> ChatSessionView:
    async with request.app.state.session_factory() as db:
        conversation = await SqlConversationStore(db).create(
            kind="chat",
            user_id=principal.user_id,
            title=payload.title or "新会话",
            model_ref=payload.model_ref,
        )
        await db.commit()
    return _session_view(conversation)


@router.get("/sessions")
async def list_sessions(
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> list[ChatSessionView]:
    async with request.app.state.session_factory() as db:
        conversations = await SqlConversationStore(db).list_for_user(principal.user_id)
    return [_session_view(conversation) for conversation in conversations]


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str,
    request: Request,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> list[ChatMessageView]:
    async with request.app.state.session_factory() as db:
        store = SqlConversationStore(db)
        await store.require_owner(_ref(session_id), principal.user_id)
        messages = await store.history(_ref(session_id), before=before, limit=limit)
    return [_message_view(message) for message in messages]


@router.put("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_session(
    session_id: str,
    payload: SessionUpdateRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> None:
    async with request.app.state.session_factory() as db:
        await SqlConversationStore(db).update_title(
            _ref(session_id), principal.user_id, payload.title
        )
        await db.commit()


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> None:
    async with request.app.state.session_factory() as db:
        await SqlConversationStore(db).delete(_ref(session_id), principal.user_id)
        await db.commit()


@router.post("/sessions/{session_id}/stream")
async def stream_reply(
    session_id: str,
    payload: StreamRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> StreamingResponse:
    state = request.app.state
    registry: ModelRegistry = state.model_registry

    try:
        spec = await registry.resolve(payload.model_ref)
        api_key = registry.api_key(spec)
    except LlmConfigError as exc:
        # Honest failure: never call a vendor we cannot authenticate to.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    gateway = state.llm_gateway_factory(spec, api_key)
    service = ChatService(state.session_factory, resilience=state.ai_resilience)
    heartbeat = state.settings.sse_heartbeat_seconds

    return StreamingResponse(
        _sse_frames(
            service,
            session=_ref(session_id),
            user_id=principal.user_id,
            payload=payload,
            gateway=gateway,
            heartbeat_seconds=heartbeat,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _sse_frames(
    service: ChatService,
    *,
    session: SessionRef,
    user_id: str,
    payload: StreamRequest,
    gateway: Any,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    """Producer/queue split so a heartbeat timeout never cancels the model stream."""
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for event in service.stream_reply(
                session=session,
                user_id=user_id,
                content=payload.content,
                gateway=gateway,
                model_ref=payload.model_ref,
                client_message_id=payload.client_message_id,
            ):
                await queue.put(event)
        except Exception:  # noqa: BLE001 - the stream must end cleanly for the client
            logger.exception("chat_stream_crashed", session_id=session.session_id)
            await queue.put(
                ChatErrorEvent(message="internal error while streaming", kind="unknown")
            )
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if event is None:
                break
            yield _encode(event)
    finally:
        producer.cancel()


def _encode(event: Any) -> str:
    if isinstance(event, ContentDelta):
        return _frame("content", {"text": event.text})
    if isinstance(event, ReasoningDelta):
        return _frame("reasoning", {"text": event.text})
    if isinstance(event, VendorMeta):
        return _frame("meta", {"model": event.model, **event.extra})
    if isinstance(event, Done):
        return _frame("done", {"finish_reason": event.finish_reason})
    if isinstance(event, ChatErrorEvent):
        return _frame("error", {"message": event.message, "kind": event.kind})
    return _frame("meta", {"unexpected": type(event).__name__})


def _frame(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
