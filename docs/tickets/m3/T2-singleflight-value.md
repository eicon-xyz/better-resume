# M3-T2 — 进程内单飞（值调用：在飞 join + 完成回放）

- blocking：M3-T1
- 纪律：先写失败测试（红），再实现（绿）；**并发用例是本票的核心证据**

## 目标

§4.1.5 的 JVM 内单飞在 Python 里的等价物：同一个 key 的并发调用只执行一次 fn，
其余调用者等待并复用同一个结果（成功或失败）。实现从 8 个 model 类 + 6 段 Lua 缩到
一个 ~150 行的类，但语义不减：**在飞合并**、**完成回放**、**TTL 惰性清理**、**条目上限**、**打点**。

## 交付物

- ai_resilience/singleflight.py：
  - Flight：state ∈ {RUNNING, DONE, FAILED}、result、error、expires_at、waiters
  - SingleFlight：async execute(key, fn, *, replay_ttl, negative_ttl) -> T
    - 无条目 / 已过期 → 当 leader，登记 RUNNING 后执行 fn
    - RUNNING → follower，await 同一个 future（**不重复调用**）
    - DONE 且在 replay_ttl 内 → 直接返回缓存值（命中计数 +1）；否则当新 leader 重跑
    - FAILED 且在 negative_ttl 内 **且** 错误标记 cacheable=True → 重放异常；否则重跑
    - max_entries（默认 256）超限时惰性清理已过期条目；仍超限则拒绝新登记（记日志，直通执行）
  - leader 异常必须广播给所有 follower（不能只让 leader 看到）
  - follower 取消（客户端断线）不影响 leader 与其他 follower
- ai_resilience/metrics.py：ResilienceMetrics（leader/follower/replay_hit/error 计数 +
  snapshot()），T7 汇总成端点
- 测试：tests/ai_resilience/test_singleflight.py（≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 并发同 key（10 个 gather） | fn 恰好被调用 **1** 次；10 个结果相同；leader=1/follower=9 |
| 不同 key | 各调 1 次，互不等待 |
| 完成后 TTL 内再调 | 不再执行 fn（replay_hit=1） |
| TTL 过期（假时钟推进） | 重新执行 fn |
| replay_ttl=0（chat 场景） | 完成后立即再调 → 重新执行（**不做完成回放**） |
| leader 抛可缓存异常 | 所有 follower 收到同一异常；TTL 内重放；TTL 后重跑 |
| leader 抛不可缓存异常（超时） | follower 收到异常，但下一次调用立刻重跑（M2「失败可重答」不变量） |
| follower 取消 | leader 照常完成，其他 follower 拿到结果 |
| 条目上限 | 超过 max_entries 不死锁、不泄漏（数量断言 + 过期清理） |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_singleflight.py | 全绿，且并发用例断言 calls == 1 |
| 反例校验 | 把 SingleFlight 换成 DirectAiResilience 跑同一用例 → 必然红（证明测试有鉴别力） |

## 不做

- 不做 Redis/跨进程（M6）；不做结果序列化（进程内直接引用）；不做后台清理任务（惰性清理足够，
  且避免"测试里蹦出一个后台任务"的经典坑——这条记进 PROBLEMS）。

