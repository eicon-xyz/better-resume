"""Scene -> gateway resolution (M5-T2): the seam that makes provider switching a config change.

The resolver owns three things and nothing else: which binding a scene has today (cached),
how to materialise a gateway for that binding, and how to describe both honestly to the API.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .binding_store import SceneBinding, SceneBindingStore
from .errors import LlmConfigError
from .factory import build_llm_gateway
from .protocols import LlmGateway
from .registry import ModelRegistry
from .scenes import AdapterKind, LlmScene, scene_label

logger = structlog.get_logger("better_resume.llm_gateway.resolver")

#: What every scene runs on out of the box (mirrors the M5-T1 migration seed).
DEFAULT_ADAPTER = AdapterKind.OPENAI_COMPAT
DEFAULT_TARGET_REF = "deepseek-flash"


@dataclass(frozen=True, slots=True)
class SceneView:
    """Public projection: no credentials, just what is bound and whether it can run."""

    scene: LlmScene
    label: str
    adapter: AdapterKind
    target_ref: str
    configured: bool
    is_default: bool


GatewayBuilder = Callable[[Any, str], LlmGateway]


async def _call(factory: GatewayFactory, name: str, binding: SceneBinding) -> object | None:
    """Factories may answer sync (vendor adapter) or async (registry lookup): accept both."""
    method = getattr(factory, name, None)
    if method is None:
        return None
    result = method(binding)
    if inspect.isawaitable(result):
        return await result
    return result


async def is_configured(factory: GatewayFactory, binding: SceneBinding) -> bool:
    return bool(await _call(factory, "is_configured", binding))


async def credential_hint(factory: GatewayFactory, binding: SceneBinding) -> str | None:
    """Optional factory hook: the missing credential name, so the 503 is actionable."""
    hint = await _call(factory, "credential_hint", binding)
    return str(hint) if hint else None


@runtime_checkable
class GatewayFactory(Protocol):
    """One per adapter kind: knows if it *can* run a binding and how to build the gateway."""

    def is_configured(self, binding: SceneBinding) -> bool: ...

    async def build(self, binding: SceneBinding) -> LlmGateway: ...


class OpenAiCompatFactory:
    """Wraps the existing model registry: target_ref is a model name, the key lives in env."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        gateway_builder: Callable[[], GatewayBuilder] | None = None,
    ) -> None:
        self._registry = ModelRegistry(session_factory)
        # Resolved lazily so tests can swap app.state.llm_gateway_factory after startup.
        self._gateway_builder = gateway_builder or (lambda: build_llm_gateway)

    async def is_configured(self, binding: SceneBinding) -> bool:
        try:
            spec = await self._registry.resolve(binding.target_ref)
        except Exception:  # noqa: BLE001 - unknown/disabled model is simply "not configured"
            return False
        return self._registry.is_configured(spec)

    async def credential_hint(self, binding: SceneBinding) -> str | None:
        """Which environment variable the operator has to set (None when nothing is missing)."""
        try:
            spec = await self._registry.resolve(binding.target_ref)
        except Exception:  # noqa: BLE001 - an unknown model has no variable to name
            return None
        if self._registry.is_configured(spec):
            return None
        return spec.api_key_env

    async def build(self, binding: SceneBinding) -> LlmGateway:
        return await self.build_for_model(binding.target_ref)

    async def build_for_model(self, model_ref: str | None) -> LlmGateway:
        """Explicit model selection (the M1 model picker) keeps working through this path."""
        spec = await self._registry.resolve(model_ref)
        # api_key() raises LlmConfigError with the variable name when the env var is missing.
        return self._gateway_builder()(spec, self._registry.api_key(spec))


class SceneResolver:
    """Binding cache + gateway materialisation. One instance per app (state.scene_resolver)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        factories: dict[AdapterKind, GatewayFactory] | None = None,
        gateway_builder: Callable[[], GatewayBuilder] | None = None,
        cache_ttl_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._factories: dict[AdapterKind, GatewayFactory] = factories or {
            AdapterKind.OPENAI_COMPAT: OpenAiCompatFactory(
                session_factory, gateway_builder=gateway_builder
            )
        }
        #: scene -> (binding, cached_at). The TTL is what makes a PUT reach other replicas.
        self._bindings: dict[LlmScene, tuple[SceneBinding, float]] = {}
        self._cache_ttl = max(0.0, cache_ttl_seconds)
        self._clock = clock
        self._lock = asyncio.Lock()
        self._loads = 0

    @property
    def loads(self) -> int:
        """How many times bindings were read from the database (cache assertions)."""
        return self._loads

    def register_factory(self, kind: AdapterKind, factory: GatewayFactory) -> None:
        self._factories[kind] = factory

    def invalidate(self, scene: LlmScene | None = None) -> None:
        if scene is None:
            self._bindings.clear()
        else:
            self._bindings.pop(scene, None)

    async def binding_for(self, scene: LlmScene) -> SceneBinding:
        async with self._lock:
            cached = self._bindings.get(scene)
            if cached is not None and self._clock() - cached[1] < self._cache_ttl:
                return cached[0]
            if cached is not None:
                # Stale: another replica changed it (or the row moved on). Re-read below.
                self._bindings.pop(scene, None)
            async with self._session_factory() as session:
                self._loads += 1
                binding = await SceneBindingStore(session).get(scene)
            if binding is None:
                raise LlmConfigError(
                    f"scene {scene.value!r} has no binding; set one via PUT /api/v1/scenes/"
                    f"{scene.value}"
                )
            self._bindings[scene] = (binding, self._clock())
            return binding

    async def resolve_model(self, model_ref: str | None) -> LlmGateway:
        """Explicit model_ref override (chat picker); bypasses scene bindings on purpose."""
        factory = self._factories.get(AdapterKind.OPENAI_COMPAT)
        builder = getattr(factory, "build_for_model", None)
        if builder is None:
            raise LlmConfigError("this build has no openai-compatible provider")
        return await builder(model_ref)

    async def resolve(self, scene: LlmScene) -> LlmGateway:
        binding = await self.binding_for(scene)
        factory = self._factories.get(binding.adapter)
        if factory is None:
            raise LlmConfigError(
                f"scene {scene.value!r} is bound to adapter {binding.adapter.value!r}, "
                "which this build does not provide"
            )
        if not await is_configured(factory, binding):
            detail = (
                f"scene {scene.value!r} ({binding.adapter.value}:{binding.target_ref}) "
                "is not configured"
            )
            missing = await credential_hint(factory, binding)
            raise LlmConfigError(
                f"{detail}: set {missing}" if missing else f"{detail}; credentials are missing"
            )
        gateway = await factory.build(binding)
        logger.debug(
            "scene_resolved",
            scene=scene.value,
            adapter=binding.adapter.value,
            target=binding.target_ref,
        )
        return gateway

    async def views(self) -> list[SceneView]:
        async with self._session_factory() as session:
            self._loads += 1
            bindings = await SceneBindingStore(session).list_all()

        views: list[SceneView] = []
        for scene in LlmScene:
            binding = bindings.get(scene)
            if binding is None:
                views.append(
                    SceneView(
                        scene=scene,
                        label=scene_label(scene),
                        adapter=DEFAULT_ADAPTER,
                        target_ref="",
                        configured=False,
                        is_default=False,
                    )
                )
                continue
            factory = self._factories.get(binding.adapter)
            views.append(
                SceneView(
                    scene=scene,
                    label=scene_label(scene),
                    adapter=binding.adapter,
                    target_ref=binding.target_ref,
                    configured=bool(factory) and await is_configured(factory, binding),
                    is_default=(
                        binding.adapter is DEFAULT_ADAPTER
                        and binding.target_ref == DEFAULT_TARGET_REF
                    ),
                )
            )
        return views
