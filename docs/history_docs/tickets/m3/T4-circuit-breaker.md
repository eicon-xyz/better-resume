# M3-T4 — 熔断器（滑动窗口 / 开态 / 半开）

- blocking：M3-T1
- 纪律：先写失败测试（红），再实现（绿）；**时间全部来自注入的 Clock，测试零真实等待**

## 目标

§4.1.4 的 CircuitBreaker：按 stage 建实例，滑动窗口统计失败率，超阈值进入开态，
开态等待期后放少量探测请求（半开），探测成功回到闭态，失败重新开态并**重新计时**。

## 交付物

- ai_resilience/breaker.py：
  - CircuitBreaker：state ∈ {CLOSED, OPEN, HALF_OPEN}、allow() -> bool、record_success()、record_failure()
  - 判定：窗口内样本数 ≥ min_calls 且失败率 ≥ failure_rate → OPEN（记 opened_at）
  - OPEN：now - opened_at < open_seconds → 拒绝（抛 AiUnavailable，**不触碰上游**）；到期 → HALF_OPEN
  - HALF_OPEN：最多 half_open_permits 个在飞探测；成功一个 → CLOSED（清窗口）；
    失败 → OPEN 且 opened_at 重置
  - 窗口用定长 deque（样本数窗口，对齐旧项目"滑动窗口 50"）
  - 每个 stage 一个实例（BreakerRegistry），互不影响
- 测试：tests/ai_resilience/test_breaker.py（≥12 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 窗口内失败率达标 | 状态转移 CLOSED → OPEN，且下一次调用短路（上游 0 次） |
| 样本不足 min_calls | 即使 100% 失败也不开（避免冷启动误开） |
| 开态等待期（假时钟） | 未到期一律短路；到期后放行半开 |
| 半开探测成功 | 回 CLOSED，窗口清空 |
| 半开探测失败 | 回 OPEN，等待期重新从当前时刻计 |
| 半开并发上限 | 第 half_open_permits+1 个探测被拒（AiUnavailable） |
| 多 stage 隔离 | extraction 熔断不影响 evaluation |
| 熔断错误分类 | 抛 AiUnavailable，retryable=True，stage 正确 |
| 快照 | snapshot() 给出 state / 窗口失败率 / 剩余开态时间（供 stats 端点） |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_breaker.py | 全绿，且用例总耗时 < 1s（证明用的是假时钟） |

## 不做

- 不做多实例共享熔断状态（M6）；不做按模型/供应商分桶（M3 只按 stage，够用且可讲清）；
  不做自动重试（重试 owner 是 llm-gateway）。

