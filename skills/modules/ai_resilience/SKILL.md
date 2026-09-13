# ai-resilience

## 职责

把单飞（进程内 + Redis）、熔断、舱壁、超时、限流收进一个 `run(stage, key, fn)`。

## 对外接口

`ResilientAiResilience`、`DistributedAiResilience`、`StagePolicies`、`SingleFlight`、
`StreamBroadcast`、`CircuitBreaker`、`Bulkhead`、`RateLimiter`、`Clock/ManualClock`。

## 不变量

1. 装饰顺序固定：单飞 → 熔断 → 舱壁 → 超时 → 上游；舱壁拒绝**不计入**熔断失败样本。
2. 重试只有一个 owner（llm-gateway）；这里绝不叠加第二层重试。
3. 聊天流的单飞是**广播**：单生产者 + 多消费者游标，迟到订阅从头回放，全部离开才取消上游。
4. 回放策略按 stage：chat 0；评分/追问/报告 60s；出题 300s；只有**不可重试**失败才负缓存。
5. 跨实例单飞：**先查结果再抢 owner**（否则会重跑已完成的活，M6 P2）。

## 已知陷阱

- 时间全部走注入的 `Clock`：`ManualClock` 只唤醒已注册的 sleeper，测试要先 settle 再 advance（M4 P5）；
  有界等待类的用例用真实短超时（M6 P3：ManualClock + 轮询循环 = 死循环，跑到超时被杀）。
- 流式调用不进跨实例回放（连接是单实例的），文档里写明。
- 结果编解码只允许 `better_resume.*` 的 Pydantic 模型；其它类型静默不回放（M6 P4：测试模型被白名单拒绝过）。
- 回放失败结果时重建异常要带全参数，漏一个关键字参数就会在 follower 上抛 TypeError（M6 P5）。

## 测试地图

`tests/ai_resilience/`（78 例，假时钟）+ `tests/test_distributed_lock.py` / `test_distributed_flight.py`（真 Redis）。

## 常见变更配方

加一个 stage：`Stage` 枚举 → `ResilienceSettings` 预算 → `StagePolicies.from_settings` → 契约/路由用例。
