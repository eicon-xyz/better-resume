"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .ai_resilience import DirectAiResilience
from .conversation import ConversationConflictError, ConversationNotFoundError
from .db import build_engine, build_session_factory
from .http import chat_router, health_router, models_router
from .identity import auth_router, build_session_store
from .llm_gateway import ModelRegistry, build_llm_gateway
from .observability import RequestIdMiddleware, configure_logging
from .settings import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = build_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.session_store = build_session_store(settings)
    app.state.model_registry = ModelRegistry(app.state.session_factory)
    # M3 swaps this for the real single-flight/breaker implementation.
    app.state.ai_resilience = DirectAiResilience()
    app.state.llm_gateway_factory = build_llm_gateway
    try:
        yield
    finally:
        await app.state.session_store.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(title=resolved.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = resolved
    app.add_middleware(RequestIdMiddleware, header_name=resolved.request_id_header)
    app.add_exception_handler(ConversationNotFoundError, _not_found)
    app.add_exception_handler(ConversationConflictError, _conflict)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(models_router)
    app.include_router(chat_router)
    return app


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """Ownership failures and missing rows are indistinguishable to the client (no leak)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app = create_app()
