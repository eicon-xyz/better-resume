"""Scene binding endpoints (M5-T2): inspect and switch providers without a redeploy."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..identity import Principal, current_principal
from ..llm_gateway import LlmScene, SceneBindingError, SceneBindingStore, SceneResolver

router = APIRouter(prefix="/api/v1/scenes", tags=["scenes"])


class SceneViewResponse(BaseModel):
    scene: str
    label: str
    adapter: str
    target_ref: str
    configured: bool
    is_default: bool


class SceneUpdateRequest(BaseModel):
    adapter: Literal["openai_compat", "xingyun"]
    target_ref: str = Field(min_length=1, max_length=128)


def _resolver(request: Request) -> SceneResolver:
    return request.app.state.scene_resolver


@router.get("", response_model=list[SceneViewResponse])
async def list_scenes(
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> list[SceneViewResponse]:
    views = await _resolver(request).views()
    return [SceneViewResponse(**asdict(view)) for view in views]


@router.put("/{scene}", response_model=SceneViewResponse)
async def update_scene(
    scene: str,
    payload: SceneUpdateRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> SceneViewResponse:
    try:
        resolved = LlmScene(scene)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown scene") from exc

    resolver = _resolver(request)
    async with request.app.state.session_factory() as session:
        try:
            await SceneBindingStore(session).upsert(resolved, payload.adapter, payload.target_ref)
        except SceneBindingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        await session.commit()

    resolver.invalidate(resolved)
    for view in await resolver.views():
        if view.scene is resolved:
            return SceneViewResponse(**asdict(view))
    raise HTTPException(status_code=500, detail="binding disappeared after the update")
