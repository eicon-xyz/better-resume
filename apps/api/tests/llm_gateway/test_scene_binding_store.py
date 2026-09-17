"""M5-T1: scene bindings — vocabulary, seeds, upsert semantics, validation."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.llm_gateway import (
    AdapterKind,
    LlmScene,
    SceneBindingError,
    SceneBindingStore,
    scene_label,
    validate_binding,
)

EXPECTED_SCENES = {
    "chat",
    "question_extraction",
    "answer_evaluation",
    "follow_up",
    "report_summary",
}


@pytest.fixture
async def factory(migrated_database: str):
    """Default bindings plus the session factory used by each case."""
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE llm_scene_bindings SET adapter='openai_compat', target_ref='deepseek-flash'"
            )
        )
        await session.commit()
    yield session_factory
    await engine.dispose()


def test_scene_enum_is_the_business_vocabulary() -> None:
    assert {scene.value for scene in LlmScene} == EXPECTED_SCENES
    assert scene_label(LlmScene.QUESTION_EXTRACTION) == "出题"
    assert scene_label(LlmScene.REPORT_SUMMARY) == "报告总结"


def test_adapter_kinds_are_the_three_real_ones() -> None:
    """P3: every kind must be a real, reachable implementation — no speculative enum values."""
    assert {kind.value for kind in AdapterKind} == {"openai_compat", "xingyun", "dashscope_app"}


def test_validate_binding_rejects_nonsense() -> None:
    with pytest.raises(SceneBindingError, match="unknown adapter"):
        validate_binding(LlmScene.CHAT, "bedrock", "x")
    with pytest.raises(SceneBindingError, match="unknown scene"):
        validate_binding("legacy_scene", AdapterKind.XINGYUN, "flow")
    with pytest.raises(SceneBindingError, match="target_ref"):
        validate_binding(LlmScene.CHAT, AdapterKind.XINGYUN, "   ")


def test_validate_binding_trims_and_resolves() -> None:
    binding = validate_binding(LlmScene.FOLLOW_UP, "xingyun", "  flow-1  ")

    assert binding.scene is LlmScene.FOLLOW_UP
    assert binding.adapter is AdapterKind.XINGYUN
    assert binding.target_ref == "flow-1"


async def test_every_scene_has_a_default_binding(factory) -> None:
    async with factory() as session:
        bindings = await SceneBindingStore(session).list_all()

    assert {scene.value for scene in bindings} == EXPECTED_SCENES
    assert all(binding.adapter is AdapterKind.OPENAI_COMPAT for binding in bindings.values())
    assert all(binding.target_ref == "deepseek-flash" for binding in bindings.values())


async def test_upsert_updates_instead_of_inserting(factory) -> None:
    async with factory() as session:
        store = SceneBindingStore(session)
        before = await store.get(LlmScene.CHAT)

        await store.upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-abc")
        await session.commit()

        after = await store.get(LlmScene.CHAT)
        rows = (
            await session.execute(
                text("SELECT count(*) FROM llm_scene_bindings WHERE scene='chat'")
            )
        ).scalar_one()

    assert before is not None and before.adapter is AdapterKind.OPENAI_COMPAT
    assert after is not None
    assert after.adapter is AdapterKind.XINGYUN
    assert after.target_ref == "flow-abc"
    assert rows == 1


async def test_upsert_touches_updated_at(factory) -> None:
    async with factory() as session:
        store = SceneBindingStore(session)
        await store.upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-1")
        await session.commit()
        first = (
            await session.execute(
                text("SELECT updated_at FROM llm_scene_bindings WHERE scene='chat'")
            )
        ).scalar_one()

        await asyncio.sleep(0.01)
        await store.upsert(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, "deepseek-flash")
        await session.commit()
        second = (
            await session.execute(
                text("SELECT updated_at FROM llm_scene_bindings WHERE scene='chat'")
            )
        ).scalar_one()

    assert second > first


async def test_unknown_scene_row_is_skipped(factory) -> None:
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO llm_scene_bindings (scene, adapter, target_ref) "
                "VALUES ('legacy_scene', 'xingyun', 'flow-old')"
            )
        )
        await session.commit()

        bindings = await SceneBindingStore(session).list_all()

        await session.execute(text("DELETE FROM llm_scene_bindings WHERE scene='legacy_scene'"))
        await session.commit()

    assert "legacy_scene" not in {scene.value for scene in bindings}
    assert {scene.value for scene in bindings} == EXPECTED_SCENES


async def test_missing_scene_returns_none(factory) -> None:
    async with session_scope(factory) as session:
        await session.execute(text("DELETE FROM llm_scene_bindings WHERE scene='chat'"))
        await session.commit()

        missing = await SceneBindingStore(session).get(LlmScene.CHAT)
        listed = await SceneBindingStore(session).list_all()

        await session.execute(
            text(
                "INSERT INTO llm_scene_bindings (scene, adapter, target_ref) "
                "VALUES ('chat', 'openai_compat', 'deepseek-flash')"
            )
        )
        await session.commit()

    assert missing is None
    assert LlmScene.CHAT not in listed


class session_scope:
    """Tiny helper so the last case reads like the others."""

    def __init__(self, factory) -> None:
        self._factory = factory

    async def __aenter__(self):
        self._session = self._factory()
        return await self._session.__aenter__()

    async def __aexit__(self, *exc: object) -> bool:
        return await self._session.__aexit__(*exc)
