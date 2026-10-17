"""Scene -> gateway resolution: the seam that makes provider switching a config change.

The resolver owns three things and nothing else: which binding a scene has today (cached),
how to materialise a gateway for that binding, and how to describe both honestly to the API.
"""

from __future__ import annotations

import asyncio
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

#: What every scene runs on out of the box (mirrors the migration seed).
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


@dataclass(frozen=True, slots=True)
class ConfigStatus:
    """One probe's snapshot: whether a binding can run, and the credential that is missing.

    The guard reads `status.configured`, a plain boolean. A forgotten await leaves a
    coroutine with no `configured` attribute, so it fails loudly instead of passing
    the truthiness check that the old async boolean let through (P8).
    """

    configured: bool
    missing: str | None = None

    def __bool__(self) -> bool:
        """Truthiness *is* the judgment, so `if not status:` stays correct too."""
        return self.configured


GatewayBuilder = Callable[[Any, str], LlmGateway]


@runtime_checkable
class GatewayFactory(Protocol):
    """One per adapter kind: the contract a factory must read to be called by the resolver.

    `config_status` judges whether a binding can run and names the missing credential when
    it cannot; `build` materialises the gateway for a binding and raises LlmConfigError when
    the binding cannot be honoured. `build_for_model` is the explicit model-ref path (the
    chat picker), provided by factories whose adapter kind selects by model name; the
    resolver calls it directly, so a factory that leaves it out fails with AttributeError
    naming the hook instead of a fallback answer that blames another cause.
    """

    async def config_status(self, binding: SceneBinding) -> ConfigStatus: ...

    async def build(self, binding: SceneBinding) -> LlmGateway: ...

    async def build_for_model(self, model_ref: str | None) -> LlmGateway: ...


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

    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
        """Resolve the registry row, then snapshot the env-backed key check in one value."""
        try:
            spec = await self._registry.resolve(binding.target_ref)
        except Exception:  # noqa: BLE001 - unknown/disabled model is simply "not configured"
            return ConfigStatus(configured=False)
        if self._registry.is_configured(spec):
            return ConfigStatus(configured=True)
        return ConfigStatus(configured=False, missing=spec.api_key_env)

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

    async def bind(self, scene: LlmScene, adapter: AdapterKind, target_ref: str) -> SceneBinding:
        """The binding write path: persist, then drop this process's cached copy.

        Writes go through the cache object so "write, then read" cannot see the old binding —
        a caller that forgets `invalidate()` is the drift P10 records (P18 in M5). Other
        replicas converge on the TTL; this process never waits for it.
        """
        async with self._session_factory() as session:
            binding = await SceneBindingStore(session).upsert(scene, adapter, target_ref)
            await session.commit()
        self.invalidate(scene)
        return binding

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
        """Explicit model_ref override (chat picker); bypasses scene bindings on purpose.

        The hook is a protocol member, so a factory that does not declare it fails here
        with AttributeError naming it — never with an answer that blames another cause.
        """
        factory = self._factories.get(AdapterKind.OPENAI_COMPAT)
        if factory is None:
            raise LlmConfigError("this build has no openai-compatible provider")
        return await factory.build_for_model(model_ref)

    async def resolve(self, scene: LlmScene) -> LlmGateway:
        binding = await self.binding_for(scene)
        factory = self._factories.get(binding.adapter)
        if factory is None:
            raise LlmConfigError(
                f"scene {scene.value!r} is bound to adapter {binding.adapter.value!r}, "
                "which this build does not provide"
            )
        status = await factory.config_status(binding)
        if not status.configured:
            detail = (
                f"scene {scene.value!r} ({binding.adapter.value}:{binding.target_ref}) "
                "is not configured"
            )
            raise LlmConfigError(
                f"{detail}: set {status.missing}"
                if status.missing
                else f"{detail}; credentials are missing"
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
            status = (
                await factory.config_status(binding)
                if factory is not None
                else ConfigStatus(configured=False)
            )
            views.append(
                SceneView(
                    scene=scene,
                    label=scene_label(scene),
                    adapter=binding.adapter,
                    target_ref=binding.target_ref,
                    configured=status.configured,
                    is_default=(
                        binding.adapter is DEFAULT_ADAPTER
                        and binding.target_ref == DEFAULT_TARGET_REF
                    ),
                )
            )
        return views
