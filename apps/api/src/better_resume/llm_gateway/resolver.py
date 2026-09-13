"""Scene -> gateway resolution (M5-T2): the seam that makes provider switching a config change.

The resolver owns three things and nothing else: which binding a scene has today (cached),
how to materialise a gateway for that binding, and how to describe both honestly to the API.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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


@runtime_checkable
class GatewayFactory(Protocol):
    """One per adapter kind: knows if it *can* run a binding and how to build the gateway."""

    def is_configured(self, binding: SceneBinding) -> bool: ...

    async def build(self, binding: SceneBinding) -> LlmGateway: ...


class OpenAiCompatFactory:
    """Wraps the existing model registry: target_ref is a model name, the key lives in env."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._registry = ModelRegistry(session_factory)

    async def is_configured(self, binding: SceneBinding) -> bool:
        try:
            spec = await self._registry.resolve(binding.target_ref)
        except Exception:  # noqa: BLE001 - unknown/disabled model is simply "not configured"
            return False
        return self._registry.is_configured(spec)

    async def build(self, binding: SceneBinding) -> LlmGateway:
        spec = await self._registry.resolve(binding.target_ref)
        # api_key() raises LlmConfigError with the variable name when the env var is missing.
        return build_llm_gateway(spec, self._registry.api_key(spec))


class SceneResolver:
    """Binding cache + gateway materialisation. One instance per app (state.scene_resolver)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        factories: dict[AdapterKind, GatewayFactory] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._factories: dict[AdapterKind, GatewayFactory] = factories or {
            AdapterKind.OPENAI_COMPAT: OpenAiCompatFactory(session_factory)
        }
        self._bindings: dict[LlmScene, SceneBinding] = {}
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
            if cached is not None:
                return cached
            async with self._session_factory() as session:
                self._loads += 1
                binding = await SceneBindingStore(session).get(scene)
            if binding is None:
                raise LlmConfigError(
                    f"scene {scene.value!r} has no binding; set one via PUT /api/v1/scenes/"
                    f"{scene.value}"
                )
            self._bindings[scene] = binding
            return binding

    async def resolve(self, scene: LlmScene) -> LlmGateway:
        binding = await self.binding_for(scene)
        factory = self._factories.get(binding.adapter)
        if factory is None:
            raise LlmConfigError(
                f"scene {scene.value!r} is bound to adapter {binding.adapter.value!r}, "
                "which this build does not provide"
            )
        if not factory.is_configured(binding):
            raise LlmConfigError(
                f"scene {scene.value!r} ({binding.adapter.value}:{binding.target_ref}) "
                "is not configured; check the credentials in the environment"
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
                    configured=bool(factory and factory.is_configured(binding)),
                    is_default=(
                        binding.adapter is DEFAULT_ADAPTER
                        and binding.target_ref == DEFAULT_TARGET_REF
                    ),
                )
            )
        return views
