# V1 证据：真模型端到端（四条链路 + 失败面）

- 时间：2026-09-14（CST）；栈：compose `nginx + 2×api + worker + postgres + redis`（fake-llm 未参与）
- 供应商：DeepSeek（`base_url=https://api.deepseek.com`），model id `deepseek-flash`
  （控制台显示名 "DeepSeek-V41-Flash" 对应 API 里的 `deepseek-flash`；`GET /models` 实测只返回
  `deepseek-flash` / `deepseek-v4-pro` 两个 id，种子无需改动）
- 命令：`uv run python -m scripts.real_model_smoke --base-url http://127.0.0.1:8080 --failure-probe --json /tmp/v1-real.json`
- 说明：本次运行与 V6 的 10 分钟浸泡同时进行（浸泡只有 ~1 req/s）。**功能证据不受影响**；
  V2 的延迟数字会在没有浸泡时单独跑。

## 1. 汇总（脚本输出的 summary 字段）

```json
{"steps": 10, "failed": [], "total_ms": 41284.8, "models": ["deepseek-flash"], "total_tokens": 1347}
```

**真假之分靠这里**：`usage.total_tokens=1347` 来自供应商响应里的 `meta` 帧（假供应商不返回 usage，
M6 的容量脚本因此一眼能区分真假）。`models` 只有 `deepseek-flash` 一个值。

## 2. 逐链路

| 步骤 | 耗时 | 真机结果 |
| --- | --- | --- |
| login | 19 ms | 200（会话在 Redis） |
| **chat-stream** | 7474 ms | 2265 字符；`usage={prompt 100, completion 1247, total 1347, reasoning 1204}`；模型 `deepseek-flash` |
| **question-extraction** | 8382 ms | 3 道题，字段齐全（`topic/focus_points/text`），通过 `QuestionBatch` 校验 |
| answer-1 | 6599 ms | score 50.0 → 追问（`AI_SUGGESTED`） |
| answer-1-F1 | 4910 ms | score 50.0 → 再追问 |
| answer-1-F2 | 2121 ms | score 12.0 → `FOLLOW_UP_LIMIT_REACHED`（追问上限生效，不是模型说了算） |
| answer-2 | 4505 ms | score 22.0 → 追问 |
| **finish** | 18 ms | 冻结报告：overall 33.5、6 个 turn、`summary_pending=true`（数字先返回，符合 T4 设计） |
| **report-summary(worker)** | 1009 ms | worker 用真模型写出 25 字总结（`llm_summary_used=true`） |
| failure-probe | 6247 ms | 场景绑到无凭据模型 → **503** + `scene 'chat' (openai_compat:real-smoke-broken) is not configured: set BR_REAL_SMOKE_MISSING_KEY` |

## 3. 结论与偏差

- 四条链路在真模型下全部成立，**不需要改任何业务代码**（本票没有代码改动，只有脚本 + 测试 + 本文档）。
- 真模型的 p50 在**秒级**（本机到 DeepSeek 的 RTT + 推理时间），与 M6 假上游的毫秒级不是一个量级；
  这正是 M6 容量报告 §2.4 之前留空的原因。
- 失败面：本次验了"缺凭据 → 503 且点名环境变量"。**超时 504 / 熔断 503 未在真模型下构造**
  （需要临时调小 stage 超时并重启进程），M3 已用可控时钟 + 假上游覆盖；列入未验证项而不是假装验过。
- 推理型模型的 `reasoning_tokens=1204` 说明 `deepseek-flash` 会先思考再答——这也是
  `supports_reasoning=true` 与 SSE `event: reasoning` 分流存在的理由（M1 契约）。
