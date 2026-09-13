"""Redis Stream job queue (M6-T4): the smallest thing that supports a real worker.

Deliberately not Celery/RQ/arq (D04 keeps orchestration in our code): a stream, a consumer
group, an ack, an attempt counter, a dead-letter stream and a status key are enough for the
one long task we actually have (report summary generation). Everything is exercised by
`tests/test_job_queue.py` and by the compose worker in T5.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger("better_resume.jobs")

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "duplicate"


@dataclass(frozen=True)
class Job:
    entry_id: str
    task_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int


class JobQueue:
    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = "br:jobs",
        group: str = "br:workers",
        dead_letter_stream: str | None = None,
        max_attempts: int = 3,
        status_ttl_seconds: int = 3600,
    ) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self.stream = stream
        self.group = group
        self.dead_letter_stream = dead_letter_stream or f"{stream}:dead"
        self.max_attempts = max(1, max_attempts)
        self._status_ttl = status_ttl_seconds
        self._group_ready = False

    # ---- producer side ----------------------------------------------------------

    async def enqueue(
        self, kind: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> tuple[str, bool]:
        """Returns (task_id, created). A repeated key returns the existing task id."""
        dedupe_key = f"{self.stream}:dedupe:{kind}:{idempotency_key}"
        task_id = secrets.token_urlsafe(12)
        claimed = await self._client.set(dedupe_key, task_id, nx=True, ex=self._status_ttl)
        if not claimed:
            existing = await self._client.get(dedupe_key)
            return (existing or task_id), False

        await self._client.xadd(
            self.stream,
            {"task_id": task_id, "kind": kind, "payload": json.dumps(payload), "attempts": "0"},
        )
        await self._client.hset(
            f"{self.stream}:status:{task_id}",
            mapping={"status": STATUS_QUEUED, "kind": kind, "attempts": 0},
        )
        await self._client.expire(f"{self.stream}:status:{task_id}", self._status_ttl)
        return task_id, True

    async def status(self, task_id: str) -> dict[str, Any] | None:
        data = await self._client.hgetall(f"{self.stream}:status:{task_id}")
        return data or None

    # ---- consumer side ----------------------------------------------------------

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:  # BUSYGROUP: already there
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def claim(self, *, consumer: str, count: int = 1, block_ms: int = 500) -> list[Job]:
        await self.ensure_group()
        response = await self._client.xreadgroup(
            self.group, consumer, {self.stream: ">"}, count=count, block=block_ms
        )
        jobs: list[Job] = []
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                jobs.append(
                    Job(
                        entry_id=entry_id,
                        task_id=fields.get("task_id", ""),
                        kind=fields.get("kind", ""),
                        payload=json.loads(fields.get("payload") or "{}"),
                        attempts=int(fields.get("attempts", "0")),
                    )
                )
        return jobs

    async def reclaim_stale(self, *, consumer: str, min_idle_ms: int = 60_000) -> list[Job]:
        """Take over entries another consumer claimed but never acked (crash recovery).

        XPENDING + XCLAIM instead of XAUTOCLAIM: the latter only exists from Redis 6.2 and
        our supported floor is 6.0 (the local instance and the compose image both are 6.x).
        """
        await self.ensure_group()
        # Plain XPENDING form: it already reports the per-entry idle time, and the
        # IDLE-filtered variant is Redis 6.2+ while our floor is 6.0. Filter in Python,
        # then let XCLAIM enforce the same threshold server-side.
        pending = await self._client.xpending_range(self.stream, self.group, "-", "+", 100)
        claimed: list[Job] = []
        for entry in pending or []:
            entry_id = entry.get("message_id") or entry.get("id")
            idle_ms = int(entry.get("time_since_delivered") or 0)
            if idle_ms < min_idle_ms:
                continue
            # XCLAIM (unlike XAUTOCLAIM) answers with a plain entry list, no cursor tuple.
            entries = await self._client.xclaim(
                self.stream,
                self.group,
                consumer,
                min_idle_time=min_idle_ms,
                message_ids=[entry_id],
            )
            for claimed_id, fields in entries or []:
                if not fields:
                    continue
                claimed.append(
                    Job(
                        entry_id=claimed_id,
                        task_id=fields.get("task_id", ""),
                        kind=fields.get("kind", ""),
                        payload=json.loads(fields.get("payload") or "{}"),
                        attempts=int(fields.get("attempts", "0")),
                    )
                )
        return claimed

    async def ack(self, job: Job, *, result: dict[str, Any] | None = None) -> None:
        await self._client.xack(self.stream, self.group, job.entry_id)
        await self._client.hset(
            f"{self.stream}:status:{job.task_id}",
            mapping={"status": STATUS_DONE, "result": json.dumps(result or {})},
        )
        await self._client.expire(f"{self.stream}:status:{job.task_id}", self._status_ttl)

    async def fail(self, job: Job, *, error: str) -> str:
        attempts = job.attempts + 1
        if attempts >= self.max_attempts:
            await self._client.xadd(
                self.dead_letter_stream,
                {
                    "task_id": job.task_id,
                    "kind": job.kind,
                    "payload": json.dumps(job.payload),
                    "attempts": str(attempts),
                    "error": error[:500],
                },
            )
            await self._client.xack(self.stream, self.group, job.entry_id)
            await self._client.hset(
                f"{self.stream}:status:{job.task_id}",
                mapping={"status": STATUS_FAILED, "attempts": attempts, "error": error[:500]},
            )
            await self._client.expire(f"{self.stream}:status:{job.task_id}", self._status_ttl)
            logger.error("job_dead_lettered", kind=job.kind, attempts=attempts)
            return STATUS_FAILED

        await self._client.xack(self.stream, self.group, job.entry_id)
        await self._client.xadd(
            self.stream,
            {
                "task_id": job.task_id,
                "kind": job.kind,
                "payload": json.dumps(job.payload),
                "attempts": str(attempts),
            },
        )
        await self._client.hset(
            f"{self.stream}:status:{job.task_id}",
            mapping={"status": STATUS_QUEUED, "attempts": attempts, "error": error[:500]},
        )
        await self._client.expire(f"{self.stream}:status:{job.task_id}", self._status_ttl)
        logger.warning("job_retry_scheduled", kind=job.kind, attempts=attempts)
        return STATUS_QUEUED

    async def mark_running(self, job: Job) -> None:
        await self._client.hset(
            f"{self.stream}:status:{job.task_id}",
            mapping={"status": STATUS_RUNNING, "attempts": job.attempts},
        )

    async def pending(self) -> int:
        info = await self._client.xpending(self.stream, self.group)
        return int(info.get("pending", 0)) if isinstance(info, dict) else int(info[0])

    async def close(self) -> None:
        await self._client.aclose()


def backoff_seconds(attempts: int, *, base: float = 0.5) -> float:
    return base * (2 ** max(0, attempts - 1))


def monotonic() -> float:  # small seam for tests that want to observe backoff
    return time.monotonic()
