"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .http import health_router
from .identity import auth_router, build_session_store
from .observability import RequestIdMiddleware, configure_logging
from .settings import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    app.state.session_store = build_session_store(settings)
    try:
        yield
    finally:
        await app.state.session_store.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(title=resolved.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = resolved
    app.add_middleware(RequestIdMiddleware, header_name=resolved.request_id_header)
    app.include_router(health_router)
    app.include_router(auth_router)
    return app


app = create_app()
