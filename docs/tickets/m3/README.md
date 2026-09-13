# M3 票据拆分提案（待确认）

> 依据：docs/DECISIONS.md（D04 自研编排 / D07 分布式只留接口 / D16 亮点第一顺位 / D17 只 mock 系统边界）
> + 分析文档 §4.1.4（AiCallGuardService 装饰顺序）、§4.1.5（JVM 内单飞 + 分布式单飞）、
> §12.2（ai-resilience 接口：run(stage, key, fn)）、§12.3（假时钟 + 假 Redis 驱动测试）、
> §12.4（M3 里程碑）。
> 状态：**提案，等你确认后动工**。

## 1. M3 验收（§12.4 原文）

> ai-resilience：单飞 + 熔断 + 限流接入四链路 → **并发同 key 单次调用有测试证明**

## 2. 范围边界

**做**：失败三态错误模型 + 可注入时钟；进程内单飞（值调用 join + 完成后短 TTL 回放）；
**流式单飞广播**（聊天流同 key 并发只调一次上游，后到者复用同一条流）；
按 stage 参数化的熔断 / 舱壁 / 超时；分桶限流中间件；ResilientAiResilience 装配并替换
DirectAiResilience；四条 AI 链路（chat / 出题 / 评分 / 追问 + 报告总结）接线与 key 修正；
韧性统计快照端点；假时钟驱动的故障注入测试；真模型冒烟证据。

**不做**（留给后续里程碑）：Redis 分布式单飞 / fencing token / 心跳接管 / 结果 gzip 回放（M6，D07
「不养默认关闭的死代码」）；压测脚本（M6）；语音（M4）；星云 adapter（M5）；**不引 tenacity /
circuitbreaker / SlowAPI 等库**（D04 自研轻量编排的精神：逻辑我们要能讲清、能测）。

**纪律**：红-绿 TDD；只 mock 系统边界（LLM HTTP / 时钟 / Redis）；内部模块不 mock；
小步提交说 WHAT；每票附执行证据；**实现中遇到的每个真问题记入 PROBLEMS.md**（本次你点名的要求）。

## 3. blocking 图

```
T1 失败三态 + 时钟接缝 ─┬─> T2 值单飞 ──> T7 装配 ResilientAiResilience ──> T8 四链路接线与 key 修正 ──> T10 验收
                        ├─> T3 流式广播 ─┘                                            │
                        ├─> T4 熔断 ─────┘                                            └─> T9 前端过载 UX（可并行）
                        ├─> T5 舱壁/超时 ┘
                        └─> T6 分桶限流 ──> T7
T10 ← 全部
```

| 票 | 标题 | blocking | 预估 |
| --- | --- | --- | --- |
| T1 | 失败三态（TIMEOUT/OVERLOADED/UNAVAILABLE）+ 时钟接缝 + 设置项 | M2 | 0.5 会话 |
| T2 | 进程内单飞：在飞 join + 完成回放（分 stage TTL） | T1 | 1.5 会话 |
| T3 | 流式单飞广播：单生产者 + 多消费者游标 + 迟到订阅回放 | T2 | 1.5 会话 |
| T4 | 熔断器：滑动窗口 / 开态 / 半开（假时钟驱动） | T1 | 1 会话 |
| T5 | 舱壁（按 stage 并发上限 + 等待预算）+ 超时 | T1 | 1 会话 |
| T6 | 分桶限流中间件（身份 = 会话 cookie 哈希，退化 IP）+ 429/Retry-After | T1 | 1 会话 |
| T7 | ResilientAiResilience 装配 + 统计快照端点 + main.py 替换 | T2 T3 T4 T5 T6 | 1 会话 |
| T8 | 四条链路接线与 resilience key 修正（含 M2 潜在串号缺陷） | T7 | 1 会话 |
| T9 | 前端 429/503/504 归一 + 聊天/面试的"服务繁忙"重试体验 | T8 | 0.5 会话 |
| T10 | M3 验收证据 + PROBLEMS 收口 + 简历草稿 + PR | 全部 | 0.5 会话 |

## 4. 与原方案的取舍（对齐 D 决议 + M1/M2 经验）

1. **单飞只做进程内**（D07）：Redis 版（Lua ACQUIRE_OR_JOIN / fencing / 心跳 / 回放）留 M6，
   且 M6 之前不留任何"默认关闭"的分支——一个进程内实现 + 一个 Protocol 就够了。
2. **流式单飞是本里程碑的真难点**：旧项目单飞只包"值调用"，聊天流没进单飞。
   我们对 fn() 返回 AsyncIterator 的情况做**广播扇出**：单生产者拉上游，多消费者各自游标读同一缓冲，
   迟到订阅者从头回放；全部消费者离开才取消上游。这既是并发同 key 验收的主要证据面，
   也是"把三层互斥收成一个方法"最硬的深度证明。
3. **回放（replay）分阶段**：chat **不**做完成回放（否则用户连续问同一句话会拿到旧答案）；
   评分/追问/报告短 TTL；出题较长 TTL；失败**只**负缓存"不可重试"的 schema 类失败，
   超时/过载/供应商抖动一律不缓存——保住 M2「评分失败可回滚重答」的不变量。
4. **重试只有一个 owner**：llm-gateway 已有传输 / schema 重试，resilience **不再叠加**重试，
   否则重试放大（旧项目 guard 装饰链里有 Retry，我们显式不做，写进文档避免"看起来少了"）。
5. **限流落在 HTTP 中间件而不是 run()**：run(stage, key, fn) 签名保持不变（§12.2 原样），
   四个调用点不需要为限流改动；桶按"路由类别"划分（general/read/answer/heavy/ai-call），
   身份优先用会话 cookie 的 sha256（不查 Redis、不记原文），无 cookie 退化到 IP。
6. **可观测性不引 Prometheus**：进程内计数器 + structlog 结构化事件 + 一个需要登录的
   GET /api/v1/resilience/stats 快照端点，够做验收证据也够面试讲。

## 5. 待确认项

见 OPEN-QUESTIONS.md（4 项：流式单飞语义、回放 TTL 策略、限流作用点与身份、参数取值）。

