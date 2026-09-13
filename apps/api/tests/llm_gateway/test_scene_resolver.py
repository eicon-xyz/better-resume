"""M5-T2: resolver caching, honest configuration flags, and the /scenes endpoints."""

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

    def is_configured(self, binding: SceneBinding) -> bool:
        return self.configured

    async def build(self, binding: SceneBinding) -> LlmGateway:
        self.built.append(binding)
        return object()  # type: ignore[return-value]


class AsyncFakeFactory:
    """Like the real OpenAiCompatFactory, whose check consults the model registry (async)."""

    def __init__(self, *, configured: bool = True) -> None:
        self.configured = configured

    async def is_configured(self, binding: SceneBinding) -> bool:
        return self.configured

    async def build(self, binding: SceneBinding) -> LlmGateway:
        raise AssertionError("build must not run for an unconfigured scene")


async def test_async_factory_checks_are_awaited(factory) -> None:
    """A coroutine is always truthy: forgetting the await silently disables the guard."""
    resolver = SceneResolver(
        factory, factories={AdapterKind.XINGYUN: AsyncFakeFactory(configured=False)}
    )
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.XINGYUN, "flow-async")
        await session.commit()

    with pytest.raises(LlmConfigError, match="not configured"):
        await resolver.resolve(LlmScene.CHAT)

    views = {view.scene: view for view in await resolver.views()}
    assert views[LlmScene.CHAT].configured is False


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
