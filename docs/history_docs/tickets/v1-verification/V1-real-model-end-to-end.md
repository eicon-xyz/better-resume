# V1 — 真模型端到端：四链路 + 失败面复验

- blocking：无（需要 Q1/Q2/Q3 的输入）
- 纪律：**只写真模型跑出来的结果**；失败也要留原始报错

## 目标

在真 DeepSeek 上把四条 AI 链路各跑一遍，确认 M1–M5 里"只在假供应商下验证过"的契约真的成立：
对话 SSE 流、出题（结构化 JSON）、评分 + 追问、报告总结（worker 队列路径），以及三条失败面
（超时 / 限流 429 / 熔断 503）在真供应商下的表现。

## 交付物

- `apps/api/scripts/real_model_smoke.py`（新脚本，复用 `interview_smoke.py` 的结构）：
  - `--base-url`（默认 compose 的 nginx `http://127.0.0.1:8080`）、`--model`（默认取注册表第一行）
  - 步骤：登录 → 建会话 → 传简历 → 出题（断言 `questions[*]` 字段完整 + `resume_score`）→
    答 2 题（断言 `score/feedback/missing_points` 非空、追问是否触发）→ finish（断言 `summary_pending`）
    → 轮询 `/report` 直到 worker 写出总结（断言 `llm_summary_used=true`）
  - 每步打印：`model` 字段、`usage` token、耗时；结尾打印汇总表
  - `--failure-probe`：① 用错 key 调 `/chat/stream` 断言 503 + 文案指名环境变量；② 把 stage 超时调到 0.01s
    断言 504 `kind=timeout`；③ 连续超时触发熔断后断言 503 `kind=unavailable` + `Retry-After`
- `docs/tickets/v1-verification/V1-EVIDENCE.md`：脚本原始输出（脱敏）+ 结论
- 测试：`tests/test_real_model_smoke_script.py`（MockTransport 跑通脚本逻辑，不需要真 key）

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 脚本可跑 | `--help` 退出 0；MockTransport 下完整流程 exit 0 |
| 真机四链路 | 每步 2xx；出题 JSON 通过 `QuestionBatch` 校验；报告 `llm_summary_used=true` |
| 真机 token 用量 | 每步 `usage.total_tokens > 0`（假供应商没有真实 usage，能区分真假） |
| 失败面 | 错误 key → 503 且文案含变量名；0.01s 超时 → 504；连续超时 → 503 + Retry-After |
| 证据完整 | `V1-EVIDENCE.md` 含 model/usage/耗时 + 原始错误文本 |

## 不做

- 不做并发压测（那是 V2）；不测星云/讯飞（V3/V4）；不为了让断言绿而放宽阈值。

## 预估

1 会话；约 15–20 次真模型调用（含 3 次失败面探针，失败面探针不需要真 key 也能跑一部分）。
