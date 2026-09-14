"""Cross-instance single flight on Redis (M6-T2).

Layered *under* the in-process flight from M3: the local registry still absorbs same-process
duplicates for free, and this module makes sure two *different* processes do not both call
the vendor for the same key.

Mechanism (deliberately ~1/10 of the old project's Lua suite, same semantics):

* `br:flight:owner:{key}`: SET NX PX lease, value = owner token; renewed while running;
* `br:flight:result:{key}`: JSON result with the same token, TTL = the stage's replay window;
* a waiter polls the result key, and takes over once the owner's lease is gone (fencing:
  the new token is randomised, and an old owner's write is rejected by a token compare);
* every path is bounded by `wait_seconds` → `AiOverloaded` instead of an unbounded wait.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any, TypeVar

import redis.asyncio as aioredis
import structlog

from .clock import Clock, SystemClock
from .errors import AiInvalid, AiOverloaded, AiResilienceError, FailureKind, wrap
from .metrics import ResilienceMetrics
from .models import Stage

logger = structlog.get_logger("better_resume.ai_resilience.distributed")

T = TypeVar("T")

#: Only our own models may be reconstructed from Redis (never arbitrary imports).
_ALLOWED_MODULE_PREFIX = "better_resume."

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


def _encode(value: Any) -> dict[str, Any] | None:
    """JSON-safe envelope for Pydantic values; None means "not distributable"."""
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        model_type = type(value)
        if not model_type.__module__.startswith(_ALLOWED_MODULE_PREFIX):
            return None
        return {
            "kind": "model",
            "module": model_type.__module__,
            "class": model_type.__name__,
            "payload": value.model_dump(mode="json"),
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {"kind": "scalar", "payload": value}
    return None


def _decode(envelope: dict[str, Any]) -> Any:
    if envelope.get("kind") == "scalar":
        return envelope.get("payload")
    module_name = str(envelope.get("module", ""))
    if not module_name.startswith(_ALLOWED_MODULE_PREFIX):
        raise AiInvalid(f"refusing to import {module_name!r} from Redis", stage=Stage.EXTRACTION)
    module = import_module(module_name)
    model_type = getattr(module, str(envelope.get("class")))
    return model_type.model_validate(envelope.get("payload"))


class RedisFlight:
    """Owner election + result replay for one process; share the URL with other instances."""

    def __init__(
        self,
        redis_url: str,
        *,
        lease_seconds: float = 30.0,
        wait_seconds: float = 10.0,
        poll_seconds: float = 0.1,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._lease_ms = max(1, int(lease_seconds * 1000))
        self._wait_seconds = wait_seconds
        self._poll_seconds = poll_seconds
        self._clock = clock or SystemClock()
        self.metrics = metrics or ResilienceMetrics()
        self.leader_wins = 0
        self.follower_replays = 0
        self.takeovers = 0

    @staticmethod
    def owner_key(flight_key: str) -> str:
        return f"br:flight:owner:{flight_key}"

    @staticmethod
    def result_key(flight_key: str) -> str:
        return f"br:flight:result:{flight_key}"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def execute(
        self,
        stage: Stage,
        key: str,
        fn: Callable[[], Awaitable[T]],
        *,
        replay_ttl: float,
        negative_ttl: float,
    ) -> T:
        token = secrets.token_urlsafe(16)
        deadline = self._clock.now() + self._wait_seconds
        attempts = 0

        while True:
            # Always prefer a published result over claiming: the owner releases the
            # flight *after* publishing, so "no owner" can also mean "just finished".
            cached = await self._read_result(key)
            if cached is not None:
                replayed, error = cached
                self.follower_replays += 1
                self.metrics.singleflight_replay += 1
                if error is not None:
                    raise error
                return replayed

            if await self._client.set(self.owner_key(key), token, nx=True, px=self._lease_ms):
                if attempts > 0:
                    # Somebody held this flight before us and never published: we took over.
                    self.takeovers += 1
                    logger.warning("flight_takeover", stage=stage.value)
                self.leader_wins += 1
                return await self._run_owner(stage, key, token, fn, replay_ttl, negative_ttl)

            attempts += 1
            if self._clock.now() >= deadline:
                self.metrics.overflow_rejected += 1
                raise AiOverloaded(
                    f"distributed flight for {stage.value} waited {self._wait_seconds:g}s "
                    "without a result",
                    stage=stage,
                )
            await self._clock.sleep(self._poll_seconds)

    async def _run_owner(
        self,
        stage: Stage,
        key: str,
        token: str,
        fn: Callable[[], Awaitable[T]],
        replay_ttl: float,
        negative_ttl: float,
    ) -> T:
        renew = asyncio.create_task(self._renew_loop(key, token), name="flight-renew")
        try:
            value = await fn()
        except BaseException as exc:  # noqa: BLE001 - failures are broadcast to waiters too
            renew.cancel()
            with contextlib.suppress(BaseException):
                await renew
            wrapped = exc if isinstance(exc, AiResilienceError) else wrap(exc, stage=stage)
            if wrapped.cacheable and negative_ttl > 0:
                await self._publish(key, token, None, wrapped, negative_ttl)
            await self._release(key, token)
            raise
        else:
            renew.cancel()
            with contextlib.suppress(BaseException):
                await renew
            envelope = _encode(value)
            if envelope is not None and replay_ttl > 0:
                await self._publish(key, token, envelope, None, replay_ttl)
            await self._release(key, token)
            return value

    async def _renew_loop(self, key: str, token: str) -> None:
        while True:
            await self._clock.sleep(self._lease_ms / 2000)
            if not await self._client.eval(
                _RENEW_LUA, 1, self.owner_key(key), token, self._lease_ms
            ):
                logger.warning("flight_lease_lost", key=key)
                return

    async def _release(self, key: str, token: str) -> None:
        with contextlib.suppress(Exception):
            await self._client.eval(_RELEASE_LUA, 1, self.owner_key(key), token)

    async def _publish(
        self,
        key: str,
        token: str,
        envelope: dict[str, Any] | None,
        error: AiResilienceError | None,
        ttl_seconds: float,
    ) -> None:
        """Write the result only while we still own the flight (fencing by token)."""
        if await self._client.get(self.owner_key(key)) != token:
            logger.warning("flight_result_write_rejected", key=key)
            return
        payload = json.dumps(
            {
                "token": token,
                "value": envelope,
                "error": None
                if error is None
                else {
                    "kind": error.kind.value,
                    "message": error.message,
                    "stage": error.stage.value,
                },
            }
        )
        await self._client.set(self.result_key(key), payload, ex=max(1, int(ttl_seconds)))

    async def _read_result(self, key: str) -> tuple[Any, AiResilienceError | None] | None:
        raw = await self._client.get(self.result_key(key))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        encoded_error = payload.get("error")
        if encoded_error:
            kind = FailureKind(encoded_error.get("kind", FailureKind.UNAVAILABLE.value))
            stage = Stage(encoded_error.get("stage", Stage.EVALUATION.value))
            error_type = {
                FailureKind.TIMEOUT: __import__(
                    "better_resume.ai_resilience.errors", fromlist=["AiTimeout"]
                ).AiTimeout,
                FailureKind.OVERLOADED: __import__(
                    "better_resume.ai_resilience.errors", fromlist=["AiOverloaded"]
                ).AiOverloaded,
                FailureKind.INVALID: AiInvalid,
            }.get(kind)
            from .errors import AiUnavailable

            error_type = error_type or AiUnavailable
            return None, error_type(
                str(encoded_error.get("message", "replayed failure")), stage=stage
            )
        envelope = payload.get("value")
        if envelope is None:
            return None
        return _decode(envelope), None


class DistributedAiResilience:
    """Wraps the M3 chain: local single flight first, then the Redis one (M6)."""

    def __init__(self, inner: Any, flight: RedisFlight) -> None:
        self._inner = inner
        self._flight = flight

    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        policy = self._inner._policies.for_stage(stage)  # noqa: SLF001 - same package
        if policy.is_stream:
            # Streams are connection-scoped: cross-instance replay is out of scope (documented).
            return await self._inner.run(stage, key, fn)
        return await self._inner.run(
            stage,
            key,
            lambda: self._flight.execute(
                stage,
                key,
                fn,
                replay_ttl=policy.replay_ttl,
                negative_ttl=policy.negative_ttl,
            ),
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
        await self._flight.aclose()
