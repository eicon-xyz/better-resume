"""P3: the DashScope application factory + resolver wiring (the third adapter kind)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.llm_gateway import (
    AdapterKind,
    LlmConfigError,
    LlmScene,
    SceneBinding,
    SceneBindingStore,
    SceneResolver,
)
from better_resume.llm_gateway.adapters.dashscope_app import DashScopeAppAdapter
from better_resume.llm_gateway.dashscope_app_factory import API_KEY_ENV, DashScopeAppFactory


@pytest.fixture
async def session_factory(migrated_database: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def binding(target_ref: str = "app-123") -> SceneBinding:
    return SceneBinding(
        scene=LlmScene.CHAT, adapter=AdapterKind.DASHSCOPE_APP, target_ref=target_ref
    )


def test_adapter_kind_gains_the_third_implementation() -> None:
    assert AdapterKind.DASHSCOPE_APP.value == "dashscope_app"
    assert {kind.value for kind in AdapterKind} == {"openai_compat", "xingyun", "dashscope_app"}


async def test_factory_reports_the_missing_variable_by_name() -> None:
    unconfigured = DashScopeAppFactory(api_key="")

    assert unconfigured.is_configured(binding()) is False
    assert unconfigured.credential_hint(binding()) == API_KEY_ENV
    with pytest.raises(LlmConfigError, match=API_KEY_ENV):
        await unconfigured.build(binding())


async def test_factory_needs_a_bound_app_id() -> None:
    configured = DashScopeAppFactory(api_key="sk-test")

    assert configured.is_configured(binding(target_ref="")) is False
    assert configured.is_configured(binding()) is True


async def test_factory_builds_the_adapter_from_the_binding_target() -> None:
    factory = DashScopeAppFactory(api_key="sk-test", base_url="http://127.0.0.1:1")

    gateway = await factory.build(binding(target_ref="app-xyz"))

    assert isinstance(gateway, DashScopeAppAdapter)
    assert gateway.model_name == "dashscope-app:app-xyz"
    await gateway.aclose()


async def test_resolver_resolves_a_scene_bound_to_the_app(
    session_factory: async_sessionmaker,
) -> None:
    """End to end through the seam: binding row -> factory -> adapter (real Postgres)."""
    async with session_factory() as session:
        store = SceneBindingStore(session)
        await store.upsert(LlmScene.CHAT, AdapterKind.DASHSCOPE_APP, "app-int")
        await session.commit()

    try:
        resolver = SceneResolver(
            session_factory,
            factories={AdapterKind.DASHSCOPE_APP: DashScopeAppFactory(api_key="sk-test")},
        )
        gateway = await resolver.resolve(LlmScene.CHAT)
        assert isinstance(gateway, DashScopeAppAdapter)
        assert gateway.model_name == "dashscope-app:app-int"
        await gateway.aclose()

        views = {view.scene: view for view in await resolver.views()}
        assert views[LlmScene.CHAT].adapter is AdapterKind.DASHSCOPE_APP
        assert views[LlmScene.CHAT].target_ref == "app-int"
        assert views[LlmScene.CHAT].configured is True

        missing_key = SceneResolver(
            session_factory,
            factories={AdapterKind.DASHSCOPE_APP: DashScopeAppFactory(api_key="")},
        )
        with pytest.raises(LlmConfigError, match=API_KEY_ENV):
            await missing_key.resolve(LlmScene.CHAT)
    finally:
        async with session_factory() as session:
            await session.execute(
                text(
                    "UPDATE llm_scene_bindings SET adapter='openai_compat', "
                    "target_ref='deepseek-flash' WHERE scene='chat'"
                )
            )
            await session.commit()
