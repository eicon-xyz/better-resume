# M6-T2 — Redis 分布式单飞（同一 Protocol 的第二个实现）

- blocking：M5
- 纪律：先写失败测试（红），再实现（绿）；**每一行都要被 M6-T8 的 kill 实例验收覆盖**

## 目标

M3 的单飞是进程内的。多实例下同一次答题/出题会在每个实例各调一次上游——M6 用 Redis 协调：

- 未命中任何在飞记录 → 抢 owner（`SET NX` + 单调 token），执行并写结果键（TTL = 回放窗口）；
- 已有 owner 在跑 → 短轮询结果键（心跳续租保证 owner 还活着），拿到结果则回放；
- owner 心跳停滞超过阈值 → 判死接管（新 token 更大，旧 owner 的写入被拒）；
- 结果回放用 JSON 序列化 + sha256 校验和；失败结果按 M3 的分类决定是否可回放。

## 交付物

- `ai_resilience/distributed.py`：`RedisSingleFlight`（实现与 `SingleFlight` 相同的 `execute` 签名，
  含 `replay_ttl/negative_ttl`），以及 `DistributedAiResilience` 装饰器：
  进程内单飞（快路径）→ Redis 协调（跨实例）→ 熔断/舱壁/超时（M3 原样）
- `settings/config.py`：`resilience.distributed: bool = False`、`flight_lease_seconds`、
  `flight_wait_seconds`、`flight_poll_seconds`
- key 家族：`br:flight:owner:{hash}`、`br:flight:result:{hash}`（只存摘要与序列化结果，不存密钥/PII）
- 测试：`tests/test_distributed_flight.py`（≥12 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 跨实例只调一次 | 两个独立 resolver 实例（不同 Redis 连接）并发同 key → 上游调用计数 1 |
| 结果回放 | 第二个实例拿到与第一个逐字节相同的结果（含 schema 校验后的对象） |
| TTL 内回放 | 完成后再调（另一实例）→ 直接回放，不再打上游 |
| TTL 过期重跑 | 假时钟推进 → 重新执行并写新结果 |
| owner 判死接管 | 模拟 owner 心跳停滞（不续租）→ 等待方接管并完成 |
| fencing | 旧 owner 复活后写结果被拒（token 比较），不会覆盖新结果 |
| 失败分类 | 不可重试失败短窗缓存；超时/过载不缓存（与 M3 语义一致） |
| 流式调用 | 流不跨实例回放（明确抛/或退化为本地流），文档写清边界 |
| 关闭开关 | `distributed=false` → 行为与 M3 完全一致（回归） |
| 降级 | Redis 不可达 → 记警告并退化为进程内单飞（**不阻塞业务**） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_distributed_flight.py` | 全绿 |
| 真实两实例 | tests/test_two_instances.py（同一 Redis，两个 app 实例）→ 出题/评分各只调一次上游 |

## 不做

- 不做完整 Lua ACQUIRE_OR_JOIN（用 SET NX + 轮询实现等价语义，代码量 1/10）；
- 不做跨实例的**流式**回放（SSE 属于单实例连接，文档写明）；
- 不做结果加密（键值只放摘要与业务结果，敏感字段不入 Redis）。

