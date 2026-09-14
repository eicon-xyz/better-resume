"""V1/P18: a scene binding change must reach every replica within the cache TTL.

Two api containers cache bindings in-process; a `PUT /api/v1/scenes/{scene}` only invalidates
the cache of the instance that served it. V1's failure probe (bind chat to a credential-less
model, then restore) left the *other* replica answering 503 long after the restore — the
per-process cache never expired. These tests pin the fix: a short TTL, and convergence measured
with an injected clock.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.llm_gateway import (
    AdapterKind,
    LlmScene,
    SceneBindingStore,
    SceneResolver,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE llm_scene_bindings SET adapter='openai_compat', target_ref='deepseek-flash'"
            )
        )
        await session.commit()
    await engine.dispose()


async def _upsert(factory: async_sessionmaker, target: str) -> None:
    async with factory() as session:
        await SceneBindingStore(session).upsert(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, target)
        await session.commit()


async def test_a_second_replica_converges_within_the_ttl(factory) -> None:
    clock = FakeClock()
    replica_a = SceneResolver(factory, cache_ttl_seconds=5.0, clock=clock)
    replica_b = SceneResolver(factory, cache_ttl_seconds=5.0, clock=clock)

    # Both replicas warm their cache on the same binding.
    assert (await replica_a.binding_for(LlmScene.CHAT)).target_ref == "deepseek-flash"
    assert (await replica_b.binding_for(LlmScene.CHAT)).target_ref == "deepseek-flash"

    # Replica A serves an admin change (its own cache is invalidated by the endpoint) ...
    replica_a.invalidate(LlmScene.CHAT)
    await _upsert(factory, "deepseek-v4-pro")

    # ... replica B still answers from its cache, but only until the TTL elapses.
    assert (await replica_b.binding_for(LlmScene.CHAT)).target_ref == "deepseek-flash"
    clock.advance(5.1)
    assert (await replica_b.binding_for(LlmScene.CHAT)).target_ref == "deepseek-v4-pro"


async def test_a_zero_ttl_reads_every_time(factory) -> None:
    resolver = SceneResolver(factory, cache_ttl_seconds=0.0, clock=FakeClock())

    await resolver.binding_for(LlmScene.CHAT)
    await _upsert(factory, "deepseek-v4-pro")

    assert (await resolver.binding_for(LlmScene.CHAT)).target_ref == "deepseek-v4-pro"
    assert resolver.loads == 2


async def test_invalidate_still_wins_over_the_cache(factory) -> None:
    resolver = SceneResolver(factory, cache_ttl_seconds=60.0, clock=FakeClock())

    await resolver.binding_for(LlmScene.CHAT)
    await _upsert(factory, "deepseek-v4-pro")
    resolver.invalidate(LlmScene.CHAT)

    assert (await resolver.binding_for(LlmScene.CHAT)).target_ref == "deepseek-v4-pro"


def test_default_ttl_is_short_enough_for_a_config_change_to_propagate() -> None:
    from better_resume.settings import Settings

    assert Settings(_env_file=None).scene_binding_cache_seconds <= 10.0
