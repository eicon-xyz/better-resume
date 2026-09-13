"""T3: chat orchestration — history in, stream out, both messages persisted."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.chat import ChatErrorEvent, ChatService
from better_resume.conversation import (
    ConversationNotFoundError,
    Message,
    SessionRef,
    SqlConversationStore,
)
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    LlmError,
    ReasoningDelta,
    StreamEvent,
    VendorMeta,
)

USER = "chat-user"


class FakeGateway:
    """Stands in for the HTTP boundary only."""

    def __init__(
        self,
        events: list[StreamEvent] | None = None,
        *,
        error: LlmError | None = None,
        delay: float = 0.0,
    ) -> None:
        self._events = events or []
        self._error = error
        self._delay = delay
        self.requests: list[ChatRequest] = []
        self.completed = False
        self.started = asyncio.Event()

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(req)
        self.started.set()
        for event in self._events:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield event
        self.completed = True
        if self._error is not None:
            raise self._error

    async def complete(self, req: ChatRequest) -> ChatResult:  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture
async def store_factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("TRUNCATE conversation_messages, conversations CASCADE"))
        await session.commit()
    yield factory
    await engine.dispose()


async def make_service(store_factory) -> tuple[ChatService, SessionRef]:
    async with store_factory() as session:
        store = SqlConversationStore(session)
        conversation = await store.create(kind="chat", user_id=USER, title="t")
        await session.commit()
    from better_resume.ai_resilience.passthrough import DirectAiResilience

    service = ChatService(store_factory, resilience=DirectAiResilience())
    return service, SessionRef(kind="chat", session_id=conversation.id)


async def drain(
    service: ChatService, ref: SessionRef, gateway: FakeGateway, **kwargs
) -> list[object]:
    events: list[object] = []
    async for event in service.stream_reply(
        session=ref, user_id=USER, content="你好", gateway=gateway, **kwargs
    ):
        events.append(event)
    return events


async def history(store_factory, ref: SessionRef):
    async with store_factory() as session:
        return await SqlConversationStore(session).history(ref)


async def test_success_streams_events_and_persists_both_messages(store_factory) -> None:
    service, ref = await make_service(store_factory)
    gateway = FakeGateway(
        [
            ReasoningDelta(text="先想"),
            ContentDelta(text="你好"),
            ContentDelta(text="，世界"),
            VendorMeta(model="deepseek-flash", extra={"usage": {"total_tokens": 12}}),
            Done(finish_reason="stop"),
        ]
    )

    events = await drain(service, ref, gateway)

    kinds = [type(event).__name__ for event in events]
    assert kinds == ["ReasoningDelta", "ContentDelta", "ContentDelta", "VendorMeta", "Done"]

    stored = await history(store_factory, ref)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[0].content == "你好"
    assert stored[1].content == "你好，世界"
    assert stored[1].reasoning == "先想"
    assert stored[1].token_count == 12
    assert stored[1].error_message is None


async def test_history_is_sent_to_the_model(store_factory) -> None:
    service, ref = await make_service(store_factory)
    async with store_factory() as session:
        store = SqlConversationStore(session)
        await store.append(ref, Message(role="user", content="第一问"))
        await store.append(ref, Message(role="assistant", content="第一答"))
        await session.commit()

    gateway = FakeGateway([ContentDelta(text="ok")])
    await drain(service, ref, gateway)

    sent = [m.content for m in gateway.requests[0].messages]
    assert sent == ["第一问", "第一答", "你好"]
    assert gateway.requests[0].messages[0].role == "user"


async def test_vendor_failure_still_records_an_assistant_message(store_factory) -> None:
    service, ref = await make_service(store_factory)
    from better_resume.llm_gateway import FailureKind, LlmTimeoutError

    gateway = FakeGateway([ContentDelta(text="半句")], error=LlmTimeoutError("boom"))

    events = await drain(service, ref, gateway)

    assert isinstance(events[-1], ChatErrorEvent)
    assert events[-1].kind == FailureKind.RETRYABLE.value

    stored = await history(store_factory, ref)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[1].content == "半句"
    assert stored[1].error_message


async def test_duplicate_client_message_id_is_not_charged_twice(store_factory) -> None:
    service, ref = await make_service(store_factory)
    first = FakeGateway([ContentDelta(text="第一次")])
    await drain(service, ref, first, client_message_id="cm-42")

    replay = FakeGateway([ContentDelta(text="不该发生")])
    events = await drain(service, ref, replay, client_message_id="cm-42")

    assert replay.requests == []
    assert len(events) == 1
    assert isinstance(events[0], ChatErrorEvent)
    assert events[0].kind == "duplicate_request"
    assert len(await history(store_factory, ref)) == 2


async def test_foreign_session_is_not_found(store_factory) -> None:
    service, ref = await make_service(store_factory)

    with pytest.raises(ConversationNotFoundError):
        async for _ in service.stream_reply(
            session=ref, user_id="intruder", content="你好", gateway=FakeGateway([])
        ):
            pass


async def test_cancellation_persists_partial_answer(store_factory) -> None:
    service, ref = await make_service(store_factory)
    gateway = FakeGateway([ContentDelta(text="被中断的半句")], delay=0.05)

    async def consume() -> None:
        async for _ in service.stream_reply(
            session=ref, user_id=USER, content="长问题", gateway=gateway
        ):
            await asyncio.sleep(0.01)

    task = asyncio.create_task(consume())
    # Wait until the model stream really started, otherwise the cancel hits setup code.
    await asyncio.wait_for(gateway.started.wait(), timeout=5)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    stored: list = []
    for _ in range(50):  # the shielded write may land a moment after the cancel
        stored = await history(store_factory, ref)
        if len(stored) == 2:
            break
        await asyncio.sleep(0.02)

    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[1].content == "被中断的半句"
    assert stored[1].error_message == "cancelled"


def test_resilience_key_is_derived_from_stage_session_and_payload() -> None:
    from better_resume.chat.service import build_resilience_key

    key = build_resilience_key("s1", "你好")

    assert key.startswith("chat|s1|")
    assert hashlib.sha256("你好".encode()).hexdigest()[:16] in key
