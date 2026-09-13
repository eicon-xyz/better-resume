"""Model registry: resolve a model_ref to a spec and its env-backed credential (D12)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .errors import LlmConfigError
from .models import ModelSpec
from .orm import AiModelRow


class ModelRegistry:
    """Small TTL cache in front of the table; `invalidate()` after admin changes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        environ: Mapping[str, str] | None = None,
        cache_ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._environ: Mapping[str, str] = environ if environ is not None else os.environ
        self._ttl = cache_ttl_seconds
        self._clock = clock
        self._cache: list[ModelSpec] | None = None
        self._cached_at = 0.0

    async def list_enabled(self) -> list[ModelSpec]:
        now = self._clock()
        if self._cache is not None and now - self._cached_at < self._ttl:
            return self._cache

        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AiModelRow)
                        .where(AiModelRow.is_enabled.is_(True))
                        .order_by(AiModelRow.priority, AiModelRow.name)
                    )
                )
                .scalars()
                .all()
            )
        self._cache = [_to_spec(row) for row in rows]
        self._cached_at = now
        return self._cache

    async def resolve(self, model_ref: str | None = None) -> ModelSpec:
        specs = await self.list_enabled()
        if not specs:
            raise LlmConfigError("no enabled models in the registry")
        if model_ref is None:
            return specs[0]
        for spec in specs:
            if model_ref in (spec.name, spec.model_id):
                return spec
        raise LlmConfigError(f"unknown or disabled model: {model_ref}")

    def is_configured(self, spec: ModelSpec) -> bool:
        return bool(self._environ.get(spec.api_key_env))

    def api_key(self, spec: ModelSpec) -> str:
        key = self._environ.get(spec.api_key_env)
        if not key:
            raise LlmConfigError(f"environment variable {spec.api_key_env} is not set")
        return key

    def invalidate(self) -> None:
        self._cache = None


def _to_spec(row: AiModelRow) -> ModelSpec:
    return ModelSpec(
        name=row.name,
        provider=row.provider,
        base_url=row.base_url,
        model_id=row.model_id,
        api_key_env=row.api_key_env,
        max_tokens=row.max_tokens,
        temperature=row.temperature,
        system_prompt=row.system_prompt,
        supports_reasoning=row.supports_reasoning,
        is_enabled=row.is_enabled,
        priority=row.priority,
        extra=row.extra or {},
    )
