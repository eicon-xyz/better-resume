"""Factory for the Xingyun adapter: reads credentials from the environment only."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .adapters.xingyun import DEFAULT_BASE_URL, XingyunWorkflowAdapter
from .binding_store import SceneBinding
from .errors import LlmConfigError
from .protocols import LlmGateway

API_KEY_ENV = "XINGCHEN_API_KEY"
API_SECRET_ENV = "XINGCHEN_API_SECRET"  # noqa: S105 - an environment variable *name*


class XingyunGatewayFactory:
    """One factory per app; credentials never leave the environment (§D12/D17)."""

    def __init__(
        self, *, environ: Mapping[str, str] | None = None, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        self._environ = environ if environ is not None else os.environ
        self._base_url = base_url

    @property
    def credentials(self) -> tuple[str, str]:
        return self._environ.get(API_KEY_ENV, ""), self._environ.get(API_SECRET_ENV, "")

    def is_configured(self, binding: SceneBinding) -> bool:
        api_key, api_secret = self.credentials
        return bool(api_key and api_secret and binding.target_ref)

    def credential_hint(self, binding: SceneBinding) -> str | None:
        api_key, api_secret = self.credentials
        missing = [
            name
            for name, value in ((API_KEY_ENV, api_key), (API_SECRET_ENV, api_secret))
            if not value
        ]
        return " and ".join(missing) if missing else None

    async def build(self, binding: SceneBinding) -> LlmGateway:
        api_key, api_secret = self.credentials
        if not api_key or not api_secret:
            raise LlmConfigError(
                f"xingyun credentials are missing: set {API_KEY_ENV} and {API_SECRET_ENV}"
            )
        if not binding.target_ref:
            raise LlmConfigError(
                f"scene {binding.scene.value!r} has no xingyun flow_id (target_ref)"
            )
        return XingyunWorkflowAdapter(
            scene=binding.scene,
            flow_id=binding.target_ref,
            api_key=api_key,
            api_secret=api_secret,
            base_url=self._base_url,
        )
