# M3-T1 — 失败三态 + 时钟接缝 + 设置项

- blocking：M2（ai_resilience 只有 Protocol + 直通实现）
- 纪律：先写失败测试（红），再实现（绿）

## 目标

§4.1.4 把上游异常归一为三类（AI_TIMEOUT / AI_OVERLOADED / AI_UNAVAILABLE），本票定下这个
错误模型与"时间从哪来"的接缝，后面四张票都建在它上面。

## 交付物

- ai_resilience/errors.py：
  - AiResilienceError(Exception) 基类，带 kind: FailureKind、retryable: bool、stage: Stage
  - AiTimeout（retryable=True）、AiOverloaded（True）、AiUnavailable（True，熔断开态/上游不可用）
  - 不新增"限流"错误：限流是 HTTP 429，不进这条线（保持三态干净）
  - classify(exc) -> FailureKind：asyncio.TimeoutError/TimeoutError → TIMEOUT；
    BulkheadFull → OVERLOADED；LlmError 按 FailureKind.RETRYABLE 分流；其余 → UNAVAILABLE
- ai_resilience/clock.py：Clock Protocol（now() -> float、async sleep(seconds)）、
  SystemClock、ManualClock（advance(seconds) + 唤醒等待者；测试与演示共用，放 src 不放 tests）
- ai_resilience/policy.py：StagePolicy（timeout / max_concurrency / queue_wait /
  replay_ttl / negative_ttl / allow_stream_replay）+ StagePolicies.from_settings(...)
- settings/config.py：新增嵌套 ResilienceSettings（BR_RESILIENCE__*，env_nested_delimiter="__"）
  与 RateLimitSettings；默认值见 OPEN-QUESTIONS Q4
- ai_resilience/__init__.py：导出新符号；DirectAiResilience **保留**（单测里当零策略替身）

## 测试

| 用例 | 断言 |
| --- | --- |
| 三类错误的 kind/retryable | 与 §4.1.4 表格一致；str(exc) 带 stage 与原因 |
| classify() 分流 | 超时/舱壁满/可重试 LLM/校验类 LLM/未知异常 五路 |
| ManualClock | advance 后 now() 前进；sleep 被 advance 唤醒；不真等 |
| StagePolicy 默认值 | 四个 stage 的超时/并发取自 settings；改 settings 后 from_settings 跟着变 |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_errors.py tests/ai_resilience/test_clock.py tests/ai_resilience/test_policy.py | 全绿 |
| uv run python -c "from better_resume.settings import Settings; print(Settings(_env_file=None).resilience)" | 打印四个 stage 的参数 |

## 不做

- 不做重试（llm-gateway 已有，见 README §4.4）；不做错误码到 HTTP 的全局映射（T7/T8 做）；
  不引第三方 resiliency 库。

