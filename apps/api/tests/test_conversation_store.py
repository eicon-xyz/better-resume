"""T1: conversation store against a real Postgres (skipped when unreachable).

Red-green discipline: written first, they failed on import (no `SqlConversationStore`).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.conversation import (
    ConversationNotFoundError,
    Message,
    SessionRef,
    SqlConversationStore,
)

USER = "user-t1"


@pytest.fixture
async def factory(migrated_database: str) -> AsyncSession:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("TRUNCATE conversation_messages, conversations CASCADE"))
        await session.commit()
    yield session_factory
    await engine.dispose()


async def make_chat(
    session_factory, *, user_id: str = USER, title: str = "t"
) -> tuple[str, SessionRef]:
    async with session_factory() as session:
        conversation = await SqlConversationStore(session).create(
            kind="chat", user_id=user_id, title=title
        )
        await session.commit()
    return conversation.id, SessionRef(kind="chat", session_id=conversation.id)


async def test_create_returns_typed_conversation(factory) -> None:
    async with factory() as session:
        conversation = await SqlConversationStore(session).create(
            kind="chat", user_id=USER, title="你好"
        )

    assert uuid.UUID(conversation.id)
    assert conversation.kind == "chat"
    assert conversation.user_id == USER
    assert conversation.title == "你好"
    assert conversation.message_count == 0
    assert conversation.created_at is not None


async def test_append_returns_monotonic_seq(factory) -> None:
    _, ref = await make_chat(factory)

    async with factory() as session:
        store = SqlConversationStore(session)
        seqs = [await store.append(ref, Message(role="user", content=f"q{i}")) for i in range(3)]
        await session.commit()

    assert seqs == [1, 2, 3]


async def test_history_is_ascending_and_paginated(factory) -> None:
    _, ref = await make_chat(factory)
    async with factory() as session:
        store = SqlConversationStore(session)
        for i in range(5):
            await store.append(ref, Message(role="user", content=f"m{i}"))
        await session.commit()

    async with factory() as session:
        store = SqlConversationStore(session)
        latest = await store.history(ref, limit=2)
        earlier = await store.history(ref, before=latest[0].seq, limit=2)

    assert [m.content for m in latest] == ["m3", "m4"]
    assert [m.seq for m in latest] == [4, 5]
    assert [m.content for m in earlier] == ["m1", "m2"]


async def test_history_keeps_reasoning_and_meta_round_trip(factory) -> None:
    _, ref = await make_chat(factory)

    async with factory() as session:
        await SqlConversationStore(session).append(
            ref,
            Message(
                role="assistant", content="答案", reasoning="先想再答", meta={"usage": {"total": 7}}
            ),
        )
        await session.commit()

    async with factory() as session:
        stored = (await SqlConversationStore(session).history(ref))[0]

    assert stored.content == "答案"
    assert stored.reasoning == "先想再答"
    assert stored.meta == {"usage": {"total": 7}}


async def test_require_owner_rejects_other_user(factory) -> None:
    _, ref = await make_chat(factory)

    async with factory() as session:
        store = SqlConversationStore(session)
        await store.require_owner(ref, USER)  # does not raise
        with pytest.raises(ConversationNotFoundError):
            await store.require_owner(ref, "someone-else")


async def test_missing_conversation_is_not_found(factory) -> None:
    ghost = SessionRef(kind="chat", session_id=str(uuid.uuid4()))

    async with factory() as session:
        store = SqlConversationStore(session)
        with pytest.raises(ConversationNotFoundError):
            await store.append(ghost, Message(role="user", content="hi"))
        with pytest.raises(ConversationNotFoundError):
            await store.history(ghost)


async def test_kind_mismatch_is_not_found(factory) -> None:
    _, ref = await make_chat(factory)
    interview_ref = SessionRef(kind="interview", session_id=ref.session_id)

    async with factory() as session:
        with pytest.raises(ConversationNotFoundError):
            await SqlConversationStore(session).history(interview_ref)


async def test_list_for_user_and_title_update_and_delete(factory) -> None:
    first_id, ref = await make_chat(factory, title="第一个")
    await make_chat(factory, user_id="other", title="别人的")

    async with factory() as session:
        store = SqlConversationStore(session)
        mine = await store.list_for_user(USER)
        await store.update_title(ref, USER, "改名了")
        await store.delete(ref, USER)
        await session.commit()

    assert [c.id for c in mine] == [first_id]
    assert mine[0].title == "第一个"

    async with factory() as session:
        store = SqlConversationStore(session)
        with pytest.raises(ConversationNotFoundError):
            await store.history(ref)


async def test_delete_cascades_messages(factory) -> None:
    _, ref = await make_chat(factory)
    async with factory() as session:
        await SqlConversationStore(session).append(ref, Message(role="user", content="hi"))
        await session.commit()

    async with factory() as session:
        await SqlConversationStore(session).delete(ref, USER)
        await session.commit()

    async with factory() as session:
        left = await session.execute(text("SELECT count(*) FROM conversation_messages"))
    assert left.scalar_one() == 0


async def test_resending_same_client_message_id_is_idempotent(factory) -> None:
    _, ref = await make_chat(factory)

    async with factory() as session:
        store = SqlConversationStore(session)
        first = await store.append(
            ref, Message(role="user", content="你好"), client_message_id="cm-1"
        )
        replay = await store.append(
            ref, Message(role="user", content="你好"), client_message_id="cm-1"
        )
        await session.commit()

    async with factory() as session:
        stored = await SqlConversationStore(session).history(ref)

    assert first == replay == 1
    assert [m.content for m in stored] == ["你好"]


async def test_concurrent_appends_are_unique_and_contiguous(factory) -> None:
    _, ref = await make_chat(factory)

    async def append_one(index: int) -> int:
        async with factory() as session:
            seq = await SqlConversationStore(session).append(
                ref, Message(role="user", content=f"c{index}")
            )
            await session.commit()
            return seq

    seqs = await asyncio.gather(*(append_one(i) for i in range(20)))

    assert sorted(seqs) == list(range(1, 21))
    assert len(set(seqs)) == 20

    async with factory() as session:
        stored = await SqlConversationStore(session).history(ref, limit=100)
    assert [m.seq for m in stored] == list(range(1, 21))
