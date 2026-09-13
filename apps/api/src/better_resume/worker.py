"""Worker entry point (M6-T4): consume jobs until asked to stop.

Run it as `python -m better_resume.worker` (the compose service does exactly that). The
loop handles SIGTERM/SIGINT by finishing the current job and then exiting, so a redeploy
never leaves a half-processed task behind.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from .ai_resilience import ResilientAiResilience
from .db import build_engine, build_session_factory
from .interview_engine import ReportService
from .jobs.queue import Job, JobQueue, backoff_seconds
from .llm_gateway import AdapterKind, LlmScene, ModelRegistry, SceneResolver, XingyunGatewayFactory
from .settings import Settings, get_settings

logger = structlog.get_logger("better_resume.worker")

REPORT_SUMMARY = "report.summary"

# A handler receives the claimed job plus the shared runtime (db, resolver, resilience).
WorkerHandler = Callable[[Job, dict[str, Any]], Awaitable[dict[str, Any] | None]]


def build_worker_runtime(settings: Settings) -> dict[str, Any]:
    """Minimal runtime for background work (the HTTP app builds its own, richer one)."""
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    resilience = ResilientAiResilience(settings)
    resolver = SceneResolver(
        session_factory,
        gateway_builder=lambda: (
            __import__("better_resume.main", fromlist=["create_app"]).build_llm_gateway
        ),
    )
    resolver.register_factory(AdapterKind.XINGYUN, XingyunGatewayFactory())
    return {
        "engine": engine,
        "session_factory": session_factory,
        "registry": ModelRegistry(session_factory),
        "resilience": resilience,
        "resolver": resolver,
    }


async def handle_report_summary(job: Job, runtime: dict[str, Any]) -> dict[str, Any]:
    """Generate the narrative for an already-frozen report (idempotent by construction)."""
    session_id = str(job.payload["session_id"])
    user_id = str(job.payload.get("user_id") or "")
    gateway = await runtime["resolver"].resolve(LlmScene.REPORT_SUMMARY)
    service = ReportService(runtime["session_factory"], resilience=runtime["resilience"])
    summary, used = await service.generate_summary(
        session_id=session_id, user_id=user_id, gateway=gateway
    )
    return {"session_id": session_id, "summary_used": used, "chars": len(summary or "")}


HANDLERS: dict[str, WorkerHandler] = {REPORT_SUMMARY: handle_report_summary}


async def run_once(
    queue: JobQueue, runtime: dict[str, Any], *, consumer: str, block_ms: int = 500
) -> int:
    """Claim and process one batch; returns how many jobs ran."""
    jobs = await queue.claim(consumer=consumer, count=1, block_ms=block_ms)
    if not jobs:
        jobs = await queue.reclaim_stale(consumer=consumer)
    processed = 0
    for job in jobs:
        handler = HANDLERS.get(job.kind)
        if handler is None:
            await queue.fail(job, error=f"no handler for kind {job.kind!r}")
            continue
        await queue.mark_running(job)
        try:
            result = await handler(job, runtime)
        except Exception as exc:  # noqa: BLE001 - a failing job must not kill the worker
            logger.warning("job_failed", kind=job.kind, error=str(exc))
            await queue.fail(job, error=f"{type(exc).__name__}: {exc}")
            if job.attempts + 1 < queue.max_attempts:
                await asyncio.sleep(backoff_seconds(job.attempts + 1))
        else:
            await queue.ack(job, result=result)
            processed += 1
            logger.info("job_done", kind=job.kind, task_id=job.task_id)
    return processed


async def serve(settings: Settings, *, stop: asyncio.Event | None = None) -> None:
    runtime = build_worker_runtime(settings)
    queue = JobQueue(
        settings.redis_url,
        stream=settings.jobs_stream,
        max_attempts=settings.jobs_max_attempts,
    )
    stopping = stop or asyncio.Event()
    consumer = f"worker-{id(settings) & 0xFFFF:x}"
    logger.info("worker_started", stream=settings.jobs_stream, consumer=consumer)
    try:
        while not stopping.is_set():
            await run_once(queue, runtime, consumer=consumer)
    finally:
        await queue.close()
        await runtime["resilience"].aclose()
        await runtime["engine"].dispose()
        logger.info("worker_stopped")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is None:  # pragma: no cover - Windows
            continue
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


async def main() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    await serve(settings, stop=stop)


if __name__ == "__main__":
    asyncio.run(main())
