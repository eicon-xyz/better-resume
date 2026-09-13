# M3-T5 — 舱壁（按 stage 并发上限）+ 超时

- blocking：M3-T1
- 纪律：先写失败测试（红），再实现（绿）；超时与等待用假时钟/事件控制，不用真实 sleep

## 目标

§4.1.4 装饰顺序里的 Bulkhead 与 TimeLimiter：每个 stage 有并发上限与排队预算，
排队超时归一为 AiOverloaded；执行超时归一为 AiTimeout。流式调用同样有总预算
（从打开到最后一帧），且超时对每个消费者可见。

## 交付物

- ai_resilience/bulkhead.py：
  - Bulkhead：asyncio.Semaphore + queue_wait 预算；获取不到 → AiOverloaded
    （含 stage、在飞数、上限）；提供 async context manager，异常路径也释放名额
  - 在飞/排队计数与峰值进 metrics
- ai_resilience/timeout.py：
  - with_timeout(stage, timeout, awaitable) → 超时抛 AiTimeout
  - wrap_stream_timeout(stage, timeout, iterator) → 剩余预算逐帧衰减；超时向消费者抛 AiTimeout
    并取消生产者（与 T3 的广播协作）
- policy.py 提供两处预算（timeout、max_concurrency、queue_wait）
- 测试：tests/ai_resilience/test_bulkhead.py、test_timeout.py（合计 ≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 并发到上限 | 第 max_concurrency+1 个在 queue_wait 内**排队**而不是立刻失败 |
| 排队超预算 | 抛 AiOverloaded（retryable=True），且上游 0 次调用 |
| 释放后放行 | 前面完成后，排队者被放行并执行成功 |
| 计数正确 | metrics 在飞数回到 0（无泄漏：异常路径也要释放信号量） |
| 值调用超时 | 抛 AiTimeout；上游 task 被取消（用 event 断言不再继续跑） |
| 流式超时 | 消费者收到 AiTimeout；生产者被取消；其他消费者不挂死 |
| 流式正常结束 | 总耗时接近但不超过预算；无假超时（预算内慢流不误杀） |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_bulkhead.py tests/ai_resilience/test_timeout.py | 全绿 |
| 泄漏检查 | 全部用例跑完后 metrics.in_flight == 0 |

## 不做

- 不做队列优先级/公平调度；不做按用户分桶的舱壁（限流负责那件事）；
  不做上游重试放大（同上，重试不在本模块）。

