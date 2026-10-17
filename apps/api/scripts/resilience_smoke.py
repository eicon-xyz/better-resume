"""M3 证据：韧性行为，一个可运行脚本（真齿轮，供应商花费极小）。

小节
  1. 并发：N 条相同聊天流穿过真实守卫链 -> 一次供应商调用
  2. 真实供应商：一次真实 DeepSeek 调用（key 不可用时跳过并给出明确说明）
  3. 故障注入：熔断打开、甩负载、半开恢复（手动时钟，无需等待）
  4. 限流：手动时钟上的令牌桶（429 判定 + Retry-After）
  5. stats：/api/v1/resilience/stats 的载荷

运行：cd apps/api && uv run python scripts/resilience_smoke.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import structlog

from better_resume.ai_resilience import (
    AiUnavailable,
    Bucket,
    ManualClock,
    RateLimiter,
    ResilienceMetrics,
    ResilientAiResilience,
    Stage,
)
from better_resume.llm_gateway import ChatRequest, Message
from better_resume.settings import RateLimitSettings, ResilienceSettings, Settings, get_settings

structlog.configure(processors=[structlog.processors.JSONRenderer(ensure_ascii=False)])


class CountingGateway:
    """包裹真实网关，统计供应商真正被进入的次数。"""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.stream_calls = 0
        self.complete_calls = 0

    def stream(self, request: ChatRequest) -> AsyncIterator[object]:
        self.stream_calls += 1
        return self._inner.stream(request)  # type: ignore[attr-defined]

    async def complete(self, request: ChatRequest):  # type: ignore[no-untyped-def]
        self.complete_calls += 1
        return await self._inner.complete(request)  # type: ignore[attr-defined]


class FlakyGateway:
    """故障注入：失败 N 次，然后正常。"""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def complete(self, request: ChatRequest):  # type: ignore[no-untyped-def]
        from better_resume.llm_gateway import LlmTimeoutError

        self.calls += 1
        if self.calls <= self.failures:
            raise LlmTimeoutError("injected vendor timeout")
        from better_resume.chat.models import Done

        return Done(finish_reason="stop")

    def stream(self, request: ChatRequest) -> AsyncIterator[object]:  # pragma: no cover
        raise NotImplementedError


def banner(title: str) -> None:
    print("\n" + "=" * 8, title, "=" * 8)


async def section_concurrency() -> None:
    banner("1. concurrent identical chat streams")
    settings = Settings(_env_file=None)
    resilience = ResilientAiResilience(settings, metrics=ResilienceMetrics())

    class Source:
        def __init__(self) -> None:
            self.opened = 0

        async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
            self.opened += 1
            for frame in ("你", "好"):
                await asyncio.sleep(0.01)
                yield frame

    source = Source()

    async def open_stream() -> AsyncIterator[str]:
        return source.stream(ChatRequest(messages=[Message(role="user", content="hi")]))

    streams = await asyncio.gather(
        resilience.run(Stage.CHAT, "chat|smoke|default|digest", open_stream),
        resilience.run(Stage.CHAT, "chat|smoke|default|digest", open_stream),
        resilience.run(Stage.CHAT, "chat|smoke|default|digest", open_stream),
    )
    texts = []
    for stream in streams:
        texts.append("".join([frame async for frame in stream]))

    print(f"consumers            : {len(texts)}")
    print(f"upstream subscriptions: {source.opened}")
    print(f"identical payloads    : {len(set(texts)) == 1} -> {texts[0]!r}")
    print(f"metrics               : {resilience.metrics.snapshot()}")
    assert source.opened == 1, "single flight failed: the vendor was entered more than once"


async def section_real_vendor() -> bool:
    banner("2. real vendor call (DeepSeek)")
    settings: Settings = get_settings()
    if not _has_key():
        print("BR_DEEPSEEK_API_KEY is empty -> skipped")
        return False

    from better_resume.db import build_engine, build_session_factory
    from better_resume.llm_gateway import ModelRegistry, build_llm_gateway

    engine = build_engine(settings.database_url)
    try:
        registry = ModelRegistry(build_session_factory(engine))
        spec = await registry.resolve(None)
        gateway = CountingGateway(build_llm_gateway(spec, registry.api_key(spec)))
        resilience = ResilientAiResilience(settings, metrics=ResilienceMetrics())
        request = ChatRequest(messages=[Message(role="user", content="用一句话说明什么是熔断器。")])

        async def open_stream() -> AsyncIterator[object]:
            return gateway.stream(request)

        streams = await asyncio.gather(
            resilience.run(Stage.CHAT, "chat|smoke|real|digest", open_stream),
            resilience.run(Stage.CHAT, "chat|smoke|real|digest", open_stream),
        )
        texts = []
        for stream in streams:
            chunks = []
            async for event in stream:
                text = getattr(event, "text", None)
                if text:
                    chunks.append(text)
            texts.append("".join(chunks))

        print(f"model                 : {spec.model_id}")
        print(f"upstream stream calls : {gateway.stream_calls}")
        print(f"consumers             : {len(texts)}")
        print(f"answer                : {texts[0][:60]!r}")
        assert gateway.stream_calls == 1
        return True
    except Exception as exc:  # noqa: BLE001 - 冒烟必须报告，而不是崩溃
        print(f"real vendor call failed: {type(exc).__name__}: {exc}")
        print("(the rest of the evidence below does not need the vendor)")
        return False
    finally:
        await engine.dispose()


def _load_env() -> None:
    """与 interview_smoke.py 不同，这里在进程内运行，所以必须加载仓库 .env。"""
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    for candidate in (Path(".env"), Path("../../.env")):
        if candidate.exists():
            load_dotenv(candidate, override=False)
    get_settings.cache_clear()
    if not os.environ.get("BR_DEEPSEEK_API_KEY"):
        print("(no BR_DEEPSEEK_API_KEY in the environment or .env files)")


def _has_key() -> bool:
    import os

    return bool(os.environ.get("BR_DEEPSEEK_API_KEY"))


async def section_breaker() -> None:
    banner("3. breaker: open -> shed -> half-open -> closed")
    clock = ManualClock()
    settings = Settings(
        _env_file=None,
        resilience=ResilienceSettings(
            breaker_min_calls=3,
            breaker_window=5,
            breaker_open_seconds=30.0,
            breaker_half_open_permits=1,
        ),
    )
    resilience = ResilientAiResilience(settings, clock=clock, metrics=ResilienceMetrics())
    gateway = FlakyGateway(failures=3)

    async def call() -> object:
        return await gateway.complete(ChatRequest(messages=[Message(role="user", content="x")]))

    for index in range(3):
        try:
            await resilience.run(Stage.EVALUATION, f"eval|smoke|{index}", call)
        except Exception as exc:  # noqa: BLE001
            print(f"call {index}: {type(exc).__name__}")

    calls_before = gateway.calls
    try:
        await resilience.run(Stage.EVALUATION, "eval|smoke|shed", call)
    except AiUnavailable as exc:
        print(f"shedded            : {exc}")
    print(f"vendor calls delta : {gateway.calls - calls_before} (expected 0)")
    print(f"breaker state      : {resilience.stats()['breakers']['evaluation']['state']}")
    assert gateway.calls == calls_before

    clock.advance(31.0)
    await resilience.run(Stage.EVALUATION, "eval|smoke|probe", call)
    print(f"after half-open    : {resilience.stats()['breakers']['evaluation']['state']}")


async def section_rate_limit() -> None:
    banner("4. rate limiting (token buckets on a manual clock)")
    clock = ManualClock()
    limiter = RateLimiter(
        RateLimitSettings(read_per_second=2.0, burst_multiplier=1.0),
        clock=clock,
        metrics=ResilienceMetrics(),
    )
    decisions = [await limiter.check(Bucket.READ, "session:demo") for _ in range(3)]
    for index, decision in enumerate(decisions):
        print(
            f"request {index}: allowed={decision.allowed} retry_after={decision.retry_after:.2f} "
            f"scope={decision.scope.value}"
        )

    clock.advance(0.5)
    print(f"after 0.5s: allowed={(await limiter.check(Bucket.READ, 'session:demo')).allowed}")
    assert [decision.allowed for decision in decisions] == [True, True, False]


async def main() -> None:
    _load_env()
    await section_concurrency()
    real_ok = await section_real_vendor()
    await section_breaker()
    await section_rate_limit()

    banner("5. stats snapshot")
    settings = Settings(_env_file=None)
    stats = ResilientAiResilience(settings, metrics=ResilienceMetrics()).stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2)[:900])
    print("\nreal vendor section ran:", real_ok)


if __name__ == "__main__":
    asyncio.run(main())
