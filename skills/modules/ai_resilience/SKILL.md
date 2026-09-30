# ai-resilience

## 职责

把单飞（进程内 + Redis）、熔断、舱壁、超时、限流收进一个 `run(stage, key, fn)`。
限流的桶状态另有一个缝（`BucketStore`）：进程内字典，或跨副本共享的 Redis（D19）。

## 对外接口

`ResilientAiResilience`、`DistributedAiResilience`、`StagePolicies`、`SingleFlight`、
`StreamBroadcast`、`CircuitBreaker`、`Bulkhead`、`RateLimiter`、`Clock/ManualClock`、
`build_rate_limiter`、`BucketStore`（`InProcessBucketStore` / `RedisBucketStore` / `DegradingBucketStore`）、
`WallClock/ManualWallClock`。

## 不变量

1. 装饰顺序固定：单飞 → 熔断 → 舱壁 → 超时 → 上游；舱壁拒绝**不计入**熔断失败样本。
2. 重试只有一个 owner（llm-gateway）；这里绝不叠加第二层重试。
3. 聊天流的单飞是**广播**：单生产者 + 多消费者游标，迟到订阅从头回放，全部离开才取消上游。
4. 回放策略按 stage：chat 0；评分/追问/报告 60s；出题 300s；只有**不可重试**失败才负缓存。
5. 跨实例单飞：**先查结果再抢 owner**（否则会重跑已完成的活，M6 P2）。
6. 限流桶的后端按桶分：`backend=redis` 时**只有** `shared_buckets`（默认 ai_call/answer/heavy）走 Redis——
   它们限的是对外配额，多副本必须共享；`general/read` 限的是本副本自己的容量，副本变多容量也变多，留在进程内（D19）。
7. 共享后端不可用时**降级到进程内桶**（既不放行也不 503），冷却窗口内不再尝试 Redis；
   降级必须可观测：`rate_limit_degraded` 计数 + 响应头 `X-RateLimit-Scope: instance`（D19）。
8. 跨进程共享的状态只能用 `WallClock.now_ms()` 做时间运算——`Clock` 是 monotonic，两个进程的读数不可比。

## 已知陷阱

- 时间有两个缝，**别混**：`Clock`（monotonic，进程内时长与等待）与 `WallClock`（wall，跨副本共享状态）。
  把 `Clock.now()` 写进 Redis 会让某个副本的令牌永远补不回来（D19 的提案里记了这条）。
- 降级是"退回上一个已知 good 状态"，不是发明新语义：改降级行为前先问"今天的基线是什么"。
- 时间全部走注入的 `Clock`：`ManualClock` 只唤醒已注册的 sleeper，测试要先 settle 再 advance（M4 P5）；
  有界等待类的用例用真实短超时（M6 P3：ManualClock + 轮询循环 = 死循环，跑到超时被杀）。
- 流式调用不进跨实例回放（连接是单实例的），文档里写明。
- 结果编解码只允许 `better_resume.*` 的 Pydantic 模型；其它类型静默不回放（M6 P4：测试模型被白名单拒绝过）。
- 回放失败结果时重建异常要带全参数，漏一个关键字参数就会在 follower 上抛 TypeError（M6 P5）。

## 测试地图

`tests/ai_resilience/`（假时钟）+ `tests/test_distributed_lock.py` / `test_distributed_flight.py`（真 Redis）
+ `tests/ai_resilience/test_ratelimit_redis.py`（两实例共享一份配额，注入 wall-clock 验令牌恢复）
+ `tests/ai_resilience/test_ratelimit_degraded.py`（降级 / 冷却 / 恢复）+ `tests/test_ratelimit_http.py`（429 语义与 scope 头）。

## 常见变更配方

加一个 stage：`Stage` 枚举 → `ResilienceSettings` 预算 → `StagePolicies.from_settings` → 契约/路由用例。
改配额：`RateLimitSettings` → 同步 `docs/perf/M6-capacity.md` 的标定口径 → 契约用例。
改共享范围：`shared_buckets` + `test_ratelimit_routing.py`（它把取值与 `Bucket` 枚举钉在一起）。
