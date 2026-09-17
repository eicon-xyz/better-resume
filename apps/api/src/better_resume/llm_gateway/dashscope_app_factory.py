"""P3: factory for the DashScope application-call adapter.

One factory per adapter kind, like the Xingyun one: the binding row says *which* application
serves a scene (`target_ref` = app_id) and the credential only ever comes from settings
(`BR_DASHSCOPE_API_KEY`, shared with the Bailian LLM/ASR endpoints).
"""

from __future__ import annotations

from .adapters.dashscope_app import DEFAULT_BASE_URL, DashScopeAppAdapter
from .binding_store import SceneBinding
from .errors import LlmConfigError
from .protocols import LlmGateway

API_KEY_ENV = "BR_DASHSCOPE_API_KEY"  # noqa: S105 - an environment variable *name*


class DashScopeAppFactory:
    """Knows whether a binding *can* run and how to materialise the gateway."""

    def __init__(self, *, api_key: str = "", base_url: str = DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url

    def is_configured(self, binding: SceneBinding) -> bool:
        return bool(self._api_key and binding.target_ref)

    def credential_hint(self, binding: SceneBinding) -> str | None:
        return None if self._api_key else API_KEY_ENV

    async def build(self, binding: SceneBinding) -> LlmGateway:
        if not self._api_key:
            raise LlmConfigError(
                f"dashscope application credentials are missing: set {API_KEY_ENV}"
            )
        if not binding.target_ref:
            raise LlmConfigError(
                f"scene {binding.scene.value!r} has no dashscope application id (target_ref)"
            )
        return DashScopeAppAdapter(
            scene=binding.scene,
            app_id=binding.target_ref,
            api_key=self._api_key,
            base_url=self._base_url,
        )
