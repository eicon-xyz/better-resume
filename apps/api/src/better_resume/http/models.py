"""GET /api/v1/models: enabled models plus an honest "configured?" flag (D12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..identity import Principal, current_principal
from ..llm_gateway import ModelRegistry, ModelView

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models")
async def list_models(
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> list[ModelView]:
    registry: ModelRegistry = request.app.state.model_registry
    specs = await registry.list_enabled()
    return [
        ModelView(
            name=spec.name,
            model_id=spec.model_id,
            provider=spec.provider,
            supports_reasoning=spec.supports_reasoning,
            configured=registry.is_configured(spec),
            is_default=index == 0,
        )
        for index, spec in enumerate(specs)
    ]
