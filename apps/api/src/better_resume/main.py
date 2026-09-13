"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .http import health_router
from .observability import RequestIdMiddleware, configure_logging
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(title=resolved.app_name, version=__version__)
    app.state.settings = resolved
    app.add_middleware(RequestIdMiddleware, header_name=resolved.request_id_header)
    app.include_router(health_router)
    return app


app = create_app()
