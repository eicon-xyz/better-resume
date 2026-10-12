# M3-T8 — 四条链路接线 + resilience key 修正

- blocking：M3-T7
- 纪律：先写失败测试（红），再实现（绿）；**这一票会改动 M2 既有代码，回归必须全绿**

## 目标

§12.2 说"interview-engine 的四条 AI 链路、chat 链路全部只 import 这一个方法"——M1/M2 调用点
已经就位，本票做三件事：核对每条链路的 stage/key 是否**真的**满足单飞去重的语义前提、
把聊天链路的在飞去重接到 T3 的广播上、用端到端并发用例证明"同 key 单次调用"。

## 发现（M2 遗留的 key 缺陷，回放策略会把它们变成真 bug）

| 链路 | 现 key | 问题 | 修法 |
| --- | --- | --- | --- |
| 出题 question_service | gen\|{session}\|{email或姓名} | 不含简历内容摘要 / 题目数量 / 语言 → 换一份简历或改 count 会命中旧批次 | extraction\|{session}\|{count}\|{lang}\|sha256(resume_context) |
| 追问 follow_up_service | followup\|{session}\|{question_no} | **不含答案摘要**，但追问 prompt 基于答案 → 不同答案会复用同一条追问 | 追加 sha256(answer) |
| 报告总结 report_service | report\|{session} | 不含分数摘要，重开/重算场景可能复用旧总结 | 追加 sha256(overall+dimensions+missing) |
| 评分 answer_service | eval\|{session}\|{question_no}\|sha256(answer) ✅ | 已合规 | 不改 |
| 聊天 chat/service.py | chat\|{session}\|sha256(content)[:16] | 不含 model_ref → 换模型问同一句话会 join 到别的模型的流 | 追加 model_ref |

> 这些缺陷在 M2 无影响（直通实现不查表），一旦开回放就会串号——因此本票把它们作为
> **先决修复**，并把每条都记进 PROBLEMS.md（"实现中遇到的问题"）。

## 交付物

- 四处 key 构造改为显式纯函数并单测（build_generation_key / build_follow_up_key /
  build_report_key / build_resilience_key），key 内不出现原文（只出现摘要）
- chat/service.py：确认 run() 返回的是广播流（AsyncIterator 分支），
  两个并发同 key 请求共享一次上游 gateway.stream()
- 端到端并发测试：tests/test_resilience_concurrency.py
  - 值链路：两个并发 POST .../answers（不同 request_id、同答案）→ FakeGateway complete() 计数 1
  - 流链路：两个并发 POST /chat/sessions/{id}/stream（同 content）→ stream() 计数 1，
    两路 SSE 合并文本一致
  - 熔断链路：连续失败 → 开态 → 后续请求 503（AiUnavailable 映射）且上游计数不再增长
  - 限流链路：连打读端点 → 429 且带 Retry-After
- main.py 错误映射：AiUnavailable/AiOverloaded → 503、AiTimeout → 504（带 kind），
  与既有 LlmError → 502 区分开；前端据此提示（T9）

## 测试

| 用例 | 断言 |
| --- | --- |
| 四个 key 纯函数 | 同输入同 key；换答案/换模型/换 count → key 不同；key 不含答案原文 |
| 并发评分 | 上游 1 次、两路 201、分数一致 |
| 并发聊天流 | 上游 1 次、两路内容一致、结束后 assistant 消息各落各的 |
| 熔断开态 | 上游 0 次、响应 503 + kind=unavailable |
| 超时 | 504 + kind=timeout |
| M2 回归 | uv run pytest -q 全绿（324 → 更多） |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/test_resilience_concurrency.py | 全绿，含"上游恰好 1 次"断言 |
| uv run pytest -q | 全绿（无 M2 回归） |
| uv run python scripts/export_openapi.py --check | 通过 |

## 不做

- 不改 M2 的状态机/幂等/题级锁语义（只加不变量测试，证明它们与单飞不冲突）；
  不做跨请求的"结果长期缓存"（TTL 见 T2）。

