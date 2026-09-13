"""T2: model registry reads Postgres and resolves env-backed credentials."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.llm_gateway import LlmConfigError
from better_resume.llm_gateway.registry import ModelRegistry


@pytest.fixture
async def session_factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def registry(session_factory) -> ModelRegistry:
    return ModelRegistry(session_factory, environ={})


async def test_seeded_models_are_listed(registry: ModelRegistry) -> None:
    models = await registry.list_enabled()

    assert [m.name for m in models] == ["deepseek-flash", "deepseek-v4-pro"]
    assert all(m.supports_reasoning for m in models)
    assert all(m.base_url.startswith("https://") for m in models)


async def test_resolve_default_and_by_name(registry: ModelRegistry) -> None:
    assert (await registry.resolve(None)).name == "deepseek-flash"
    assert (await registry.resolve("deepseek-v4-pro")).model_id == "deepseek-v4-pro"


async def test_resolve_unknown_model_raises_config_error(registry: ModelRegistry) -> None:
    with pytest.raises(LlmConfigError):
        await registry.resolve("does-not-exist")


async def test_missing_api_key_is_reported_not_faked(registry: ModelRegistry) -> None:
    spec = await registry.resolve(None)

    assert registry.is_configured(spec) is False
    with pytest.raises(LlmConfigError):
        registry.api_key(spec)


async def test_api_key_is_read_from_environment(session_factory) -> None:
    registry = ModelRegistry(session_factory, environ={"BR_DEEPSEEK_API_KEY": "sk-test"})
    spec = await registry.resolve(None)

    assert registry.is_configured(spec) is True
    assert registry.api_key(spec) == "sk-test"


async def test_disable_takes_effect_after_cache_invalidation(session_factory) -> None:
    from sqlalchemy import text

    registry = ModelRegistry(session_factory, environ={})
    await registry.list_enabled()  # warm the cache

    async with session_factory() as session:
        await session.execute(
            text("UPDATE ai_models SET is_enabled = false WHERE name = 'deepseek-v4-pro'")
        )
        await session.commit()
    try:
        assert [m.name for m in await registry.list_enabled()] == [
            "deepseek-flash",
            "deepseek-v4-pro",
        ]
        registry.invalidate()
        assert [m.name for m in await registry.list_enabled()] == ["deepseek-flash"]
    finally:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE ai_models SET is_enabled = true WHERE name = 'deepseek-v4-pro'")
            )
            await session.commit()
