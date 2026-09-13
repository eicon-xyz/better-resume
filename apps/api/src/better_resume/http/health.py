"""Liveness endpoint used by compose/CI health checks."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
