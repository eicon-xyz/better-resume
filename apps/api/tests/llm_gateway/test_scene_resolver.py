"""resolver caching, honest configuration flags, and the /scenes endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.llm_gateway import (
    AdapterKind,
    ConfigStatus,
    LlmConfigError,
    LlmScene,
    SceneBinding,
    SceneBindingStore,
    SceneResolver,
)
from better_resume.llm_gateway.protocols import LlmGateway

from .test_scene_binding_store import EXPECTED_SCENES  # noqa: F401 - reused vocabulary


@pytest.fixture
async def factory(migrated_database: str) -> AsyncIterator[async_sessionmaker]:
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


class FakeFactory:
    """Stands in for a vendor adapter factory (a real seam, not an internal mock)."""

    def __init__(self, *, configured: bool = True) -> None:
        self.configured = configured
        self.built: list[SceneBinding] = []

    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
        return ConfigStatus(configured=self.configured)

    async def build(self, binding: SceneBinding) -> LlmGateway:
        self.built.append(binding)
        return object()  # type: ignore[return-value]


class LegacyAsyncBoolFactory:
    """The historical shape (P8): an async boolean check — a coroutine is always truthy."""

    def __init__(self, *, configured: bool = False) -> None:
        self.configured = configured
        self.checks = 0

    async def is_configured(self, binding: SceneBinding) -> bool:
        self.checks += 1
        return self.configured

    async def build(self, binding: SceneBinding) -> LlmGateway:
        return object()  # type: ignore[return-value]


async def test_legacy_async_boolean_is_not_the_seam(factory) -> None:
    """P01/P11: `if not factory.is_configured(binding)` was always false because a
    coroutine is truthy, so the guard never fired. The seam now hands out a config
    snapshot; a factory that only offers the old async boolean fails loudly here
    instead of getting a silent path through the guard."""
    legacy = LegacyAsyncBoolFactory(configured=False)
    resolver = SceneResolver(factory, factories={AdapterKind.XINGYUN: legacy})
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-legacy")
        await session.commit()

    with pytest.raises(AttributeError, match="config_status"):
        await resolver.resolve(LlmScene.CHAT)
    assert legacy.checks == 0


class NoModelPickerFactory:
    """A factory that declares the two binding hooks but not the model-selection one."""

    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
        return ConfigStatus(configured=True)

    async def build(self, binding: SceneBinding) -> LlmGateway:
        return object()  # type: ignore[return-value]


async def test_a_factory_without_model_selection_fails_loudly(factory) -> None:
    """LG-06: the picker path is a protocol member, not a getattr private contract.

    A factory that never declares `build_for_model` must fail at the call site, naming
    the missing hook. The getattr fallback instead answered "this build has no
    openai-compatible provider" — a cause that points away from the real one.
    """
    resolver = SceneResolver(factory, factories={AdapterKind.OPENAI_COMPAT: NoModelPickerFactory()})

    with pytest.raises(AttributeError, match="build_for_model"):
        await resolver.resolve_model("deepseek-flash")


async def test_model_selection_goes_through_the_factory_protocol(factory) -> None:
    """The picker hands the explicit model_ref to the openai-compatible factory."""

    class PickingFactory:
        def __init__(self) -> None:
            self.picked: list[str | None] = []

        async def config_status(self, binding: SceneBinding) -> ConfigStatus:
            return ConfigStatus(configured=True)

        async def build(self, binding: SceneBinding) -> LlmGateway:
            raise AssertionError("resolve_model must not go through the scene binding")

        async def build_for_model(self, model_ref: str | None) -> LlmGateway:
            self.picked.append(model_ref)
            return object()  # type: ignore[return-value]

    picking = PickingFactory()
    resolver = SceneResolver(factory, factories={AdapterKind.OPENAI_COMPAT: picking})

    assert await resolver.resolve_model("deepseek-v4-pro") is not None
    assert picking.picked == ["deepseek-v4-pro"]


async def test_config_status_snapshot_carries_the_missing_credential(factory) -> None:
    """One probe returns the value snapshot that both the guard and the views read."""

    class SnapshotFakeFactory:
        async def config_status(self, binding: SceneBinding) -> ConfigStatus:
            return ConfigStatus(configured=False, missing="XINGCHEN_API_KEY")

        async def build(self, binding: SceneBinding) -> LlmGateway:
            raise AssertionError("build must not run for an unconfigured scene")

    resolver = SceneResolver(factory, factories={AdapterKind.XINGYUN: SnapshotFakeFactory()})
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-snap")
        await session.commit()

    with pytest.raises(LlmConfigError, match="set XINGCHEN_API_KEY"):
        await resolver.resolve(LlmScene.CHAT)

    views = {view.scene: view for view in await resolver.views()}
    assert views[LlmScene.CHAT].configured is False
    # The snapshot is the whole judgment: bool(status) must never pass for an unconfigured one.
    assert not ConfigStatus(configured=False, missing="XINGCHEN_API_KEY")
    assert ConfigStatus(configured=True)


async def test_resolve_returns_the_bound_adapter(factory) -> None:
    fake = FakeFactory()
    resolver = SceneResolver(factory, factories={AdapterKind.XINGYUN: fake})
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-9")
        await session.commit()

    gateway = await resolver.resolve(LlmScene.CHAT)

    assert gateway is not None
    assert [binding.target_ref for binding in fake.built] == ["flow-9"]


async def test_bindings_are_cached_until_invalidated(factory) -> None:
    resolver = SceneResolver(factory)

    await resolver.binding_for(LlmScene.CHAT)
    await resolver.binding_for(LlmScene.CHAT)
    assert resolver.loads == 1

    resolver.invalidate(LlmScene.CHAT)
    await resolver.binding_for(LlmScene.CHAT)
    assert resolver.loads == 2


async def test_a_binding_write_through_the_resolver_is_read_back_immediately(factory) -> None:
    """P10: the resolver owns the binding write path, so a write drops its own cache entry.

    A caller that remembers to call `invalidate()` is exactly the seam P10 says to remove:
    with a long TTL, forgetting it means this process keeps routing the scene to the old
    binding. Writing through the resolver must be visible to the very next read.
    """
    resolver = SceneResolver(factory, cache_ttl_seconds=60.0)
    await resolver.bind(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, "deepseek-flash")
    try:
        assert (await resolver.binding_for(LlmScene.CHAT)).target_ref == "deepseek-flash"
        await resolver.bind(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, "deepseek-v4-pro")

        assert (await resolver.binding_for(LlmScene.CHAT)).target_ref == "deepseek-v4-pro"
        assert resolver.loads == 2, "写后必须重新读库，而不是等 TTL"
    finally:
        # the binding table is shared by the whole run: put chat back on the default
        await resolver.bind(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, "deepseek-flash")


async def test_missing_binding_is_a_config_error(factory) -> None:
    resolver = SceneResolver(factory)
    async with factory() as session:
        await session.execute(text("DELETE FROM llm_scene_bindings WHERE scene='chat'"))
        await session.commit()

    with pytest.raises(LlmConfigError, match="no binding"):
        await resolver.resolve(LlmScene.CHAT)


async def test_unconfigured_adapter_is_reported_not_hidden(factory) -> None:
    resolver = SceneResolver(
        factory, factories={AdapterKind.XINGYUN: FakeFactory(configured=False)}
    )
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-x")
        await session.commit()

    with pytest.raises(LlmConfigError, match="not configured"):
        await resolver.resolve(LlmScene.CHAT)

    views = {view.scene: view for view in await resolver.views()}
    assert views[LlmScene.CHAT].configured is False
    assert views[LlmScene.CHAT].target_ref == "flow-x"


async def test_views_describe_every_scene(factory) -> None:
    resolver = SceneResolver(factory)

    views = await resolver.views()

    assert {view.scene.value for view in views} == EXPECTED_SCENES
    assert all(view.adapter is AdapterKind.OPENAI_COMPAT for view in views)
    assert all(view.is_default for view in views)
    assert all(view.label for view in views)


def login(client: TestClient) -> str:
    user_id = f"scenes-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def test_scenes_endpoints_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/scenes").status_code == 401
    assert (
        client.put(
            "/api/v1/scenes/chat", json={"adapter": "xingyun", "target_ref": "flow-1"}
        ).status_code
        == 401
    )


def test_list_and_switch_a_scene(client: TestClient, app: FastAPI, migrated_database: str) -> None:
    login(client)

    listed = client.get("/api/v1/scenes")
    assert listed.status_code == 200
    payload = listed.json()
    assert {row["scene"] for row in payload} == EXPECTED_SCENES
    assert {row["adapter"] for row in payload} == {"openai_compat"}

    switched = client.put(
        "/api/v1/scenes/answer_evaluation",
        json={"adapter": "xingyun", "target_ref": "flow-eval"},
    )
    assert switched.status_code == 200
    assert switched.json()["target_ref"] == "flow-eval"
    assert switched.json()["adapter"] == "xingyun"
    assert switched.json()["configured"] is False  # no xingyun factory in this build

    after = {row["scene"]: row for row in client.get("/api/v1/scenes").json()}
    assert after["answer_evaluation"]["target_ref"] == "flow-eval"
    assert after["chat"]["target_ref"] == "deepseek-flash"

    # restore the default so other tests keep the M4 behaviour
    client.put(
        "/api/v1/scenes/answer_evaluation",
        json={"adapter": "openai_compat", "target_ref": "deepseek-flash"},
    )


def test_update_validates_scene_and_body(client: TestClient, migrated_database: str) -> None:
    login(client)

    assert (
        client.put(
            "/api/v1/scenes/nope", json={"adapter": "xingyun", "target_ref": "f"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/v1/scenes/chat", json={"adapter": "bedrock", "target_ref": "f"}
        ).status_code
        == 422
    )
    assert (
        client.put("/api/v1/scenes/chat", json={"adapter": "xingyun", "target_ref": ""}).status_code
        == 422
    )
