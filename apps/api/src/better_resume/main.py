"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .ai_resilience import (
    AiInvalid,
    AiOverloaded,
    AiResilienceError,
    AiTimeout,
    AiUnavailable,
    RateLimiter,
    ResilientAiResilience,
)
from .conversation import ConversationConflictError, ConversationNotFoundError
from .db import build_engine, build_session_factory
from .http import (
    RateLimitMiddleware,
    chat_router,
    health_router,
    interview_router,
    media_router,
    models_router,
    resilience_router,
    scenes_router,
)
from .identity import auth_router, build_session_store, build_ws_ticket_store
from .interview_engine import (
    IllegalFlowTransition,
    IllegalSessionTransition,
    InterviewEngineError,
    QuestionLockRegistry,
    SessionNotFound,
)
from .llm_gateway import LlmError, ModelRegistry, SceneResolver, build_llm_gateway
from .media import ChannelRegistry, EdgeTtsSynthesizer, TtsCache
from .observability import RequestIdMiddleware, configure_logging
from .resume_parser import ResumeParseError
from .settings import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = build_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.session_store = build_session_store(settings)
    app.state.ws_ticket_store = build_ws_ticket_store(settings)
    app.state.transcription_registry = ChannelRegistry()
    app.state.tts_synthesizer = EdgeTtsSynthesizer(
        cache=TtsCache(settings.media.tts_storage_dir),
        default_voice=settings.media.tts_voice,
    )
    app.state.model_registry = ModelRegistry(app.state.session_factory)
    # M5: scenes resolve to a gateway through their binding row (cached).
    app.state.scene_resolver = SceneResolver(app.state.session_factory)
    # M3: single flight + circuit breaker + bulkhead + deadlines behind one method.
    app.state.ai_resilience = ResilientAiResilience(settings)
    app.state.llm_gateway_factory = build_llm_gateway
    app.state.rate_limiter = RateLimiter(settings.rate_limit)
    # Process-local question locks; M6 swaps them for Redis behind the same seam.
    app.state.question_locks = QuestionLockRegistry()
    try:
        yield
    finally:
        await app.state.ai_resilience.aclose()
        await app.state.ws_ticket_store.aclose()
        await app.state.session_store.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(title=resolved.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = resolved
    # add_middleware prepends, so the request id stays the outermost layer (added last).
    app.add_middleware(RateLimitMiddleware, settings=resolved)
    app.add_middleware(RequestIdMiddleware, header_name=resolved.request_id_header)
    app.add_exception_handler(ConversationNotFoundError, _not_found)
    app.add_exception_handler(ConversationConflictError, _conflict)
    app.add_exception_handler(SessionNotFound, _not_found)
    app.add_exception_handler(IllegalSessionTransition, _conflict)
    app.add_exception_handler(IllegalFlowTransition, _conflict)
    app.add_exception_handler(InterviewEngineError, _unprocessable)
    app.add_exception_handler(ResumeParseError, _bad_request)
    app.add_exception_handler(LlmError, _bad_gateway)
    # M3 taxonomy: 504 timeout, 503 shedding/unavailable, 502 malformed upstream.
    app.add_exception_handler(AiTimeout, _gateway_timeout)
    app.add_exception_handler(AiOverloaded, _service_unavailable)
    app.add_exception_handler(AiUnavailable, _service_unavailable)
    app.add_exception_handler(AiInvalid, _bad_gateway)
    app.add_exception_handler(AiResilienceError, _service_unavailable)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(models_router)
    app.include_router(resilience_router)
    app.include_router(media_router)
    app.include_router(scenes_router)
    app.include_router(chat_router)
    app.include_router(interview_router)
    return app


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """Ownership failures and missing rows are indistinguishable to the client (no leak)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def _unprocessable(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    """Resume parsing problems are the user's input, not a server fault."""
    code = getattr(exc, "code", None)
    return JSONResponse(status_code=400, content={"detail": str(exc), "code": code})


async def _gateway_timeout(request: Request, exc: Exception) -> JSONResponse:
    kind = getattr(getattr(exc, "kind", None), "value", "timeout")
    return JSONResponse(status_code=504, content={"detail": str(exc), "kind": kind})


async def _service_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Breaker open or bulkhead full: the caller should retry later, not reword the request."""
    kind = getattr(getattr(exc, "kind", None), "value", "unavailable")
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "kind": kind},
        headers={"Retry-After": "5"},
    )


async def _bad_gateway(request: Request, exc: Exception) -> JSONResponse:
    kind = getattr(getattr(exc, "kind", None), "value", "unknown")
    return JSONResponse(status_code=502, content={"detail": str(exc), "kind": kind})


app = create_app()
