# M3-T7 — ResilientAiResilience 装配 + 统计快照端点

- blocking：M3-T2 T3 T4 T5 T6
- 纪律：先写失败测试（红），再实现（绿）

## 目标

把 T2–T6 的零件按 §4.1.4 的顺序串成一个 run()：**单飞 → 熔断 → 舱壁 → 超时 → 上游**，
失败分类三态统一出口；并把 main.py 的 DirectAiResilience 换掉。

## 交付物

- ai_resilience/resilient.py：ResilientAiResilience
  ```python
  async def run(self, stage, key, fn): ...
  # 1) single-flight（含流式广播分支）
  # 2) breaker.allow() → 不通过抛 AiUnavailable（上游 0 次）
  # 3) bulkhead（排队超时 → AiOverloaded）
  # 4) timeout（值/流两种包装 → AiTimeout）
  # 5) 记录成功/失败到 breaker 与 metrics；异常统一 classify()
  # 6) structlog 事件：ai_call_started/finished/failed/rejected（带 stage/key 摘要/耗时/结果）
  ```
  - key 只记哈希摘要进日志（key 里含会话/题目信息，避免日志噪音与潜在内容泄漏）
  - stats() -> dict：per-stage breaker 状态、在飞/排队、单飞命中、超时/过载/拒绝计数
- http/resilience.py：GET /api/v1/resilience/stats（需要登录会话，返回 stats()）
- main.py：app.state.ai_resilience = ResilientAiResilience(settings, clock=SystemClock())；
  lifespan 关闭时取消残留生产者任务（干净退出，避免 pytest 里 task 泄漏告警）
- 测试：tests/ai_resilience/test_resilient.py（≥12 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 装饰顺序 | 舱壁满时不占用熔断失败样本；熔断开态时不占用舱壁名额 |
| 直通 | 正常调用结果透传，metrics 计数 +1，structlog 事件带 stage/耗时 |
| 三类错误出口 | 上游超时 → AiTimeout；排队超时 → AiOverloaded；熔断开态 → AiUnavailable |
| 单飞 × 熔断 | 熔断打开后同 key 的在飞 follower 仍拿到结果，新调用被拒 |
| 流式经过全链 | 聊天流在单飞广播下透传，超时预算生效，取消干净 |
| 干净退出 | aclose() 后无残留 task（asyncio.all_tasks() 断言） |
| stats 端点 | 未登录 401；登录后 200 且字段齐全（四 stage + 计数） |
| settings 开关 | resilience.enabled=false → 退化成直通（单飞也不做），仍可服务 |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_resilient.py tests/test_resilience_api.py | 全绿 |
| curl -b cookies /api/v1/resilience/stats | 200，JSON 含 breaker 状态与单飞计数 |
| OpenAPI 漂移 | uv run python scripts/export_openapi.py --check 通过（新端点进契约） |

## 不做

- 不做动态改参数（重启生效）；不做 Prometheus 导出（D17）；不做定时器/后台判定任务
  （全部惰性判定，便于测试与退出）。

