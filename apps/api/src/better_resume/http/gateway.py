r"""One place where the HTTP layer turns a scene into a gateway (M5-T6).

Business services keep taking a `gateway: LlmGateway` argument (that seam is from M1); only
the *choice* of provider moved here, so switching providers never edits business code.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from ..llm_gateway import LlmConfigError, LlmGateway, LlmScene, SceneResolver


def _resolver(request: Request) -> SceneResolver:
    return request.app.state.scene_resolver


async def gateway_for(
    request: Request, scene: LlmScene, *, model_ref: str | None = None
) -> LlmGateway:
    """Scene binding, unless the caller explicitly picked a model (M1 picker compatibility)."""
    resolver = _resolver(request)
    try:
        if model_ref:
            return await resolver.resolve_model(model_ref)
        return await resolver.resolve(scene)
    except LlmConfigError as exc:
        # Honest failure: never call a vendor we cannot authenticate to.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


__all__ = ["gateway_for"]
