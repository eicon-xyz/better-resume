"""GET /api/v1/resilience/stats: the guard chain's own view of the world (M3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from ..identity import Principal, current_principal

router = APIRouter(prefix="/api/v1/resilience", tags=["resilience"])


@router.get("/stats")
async def resilience_stats(
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> dict[str, Any]:
    from ..ai_resilience import ResilientAiResilience

    service: ResilientAiResilience = request.app.state.ai_resilience
    return service.stats()
