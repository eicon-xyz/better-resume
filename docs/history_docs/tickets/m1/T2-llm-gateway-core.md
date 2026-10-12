# M1-T2 — llm-gateway：模型注册表 + OpenAICompatAdapter + schema 强校验

- blocking：M1-T1
- 纪律：先写失败测试（红），再实现（绿）；**只 mock HTTP 边界**

## 目标

落 §12.2 的 llm-gateway 真实实现：一个 `complete()` + 一个 `stream()` 吃掉所有供应商差异，
reasoning_content 归一，结构化输出强校验，换模型只改库。

## 交付物

- 迁移 `0003_ai_models`：`ai_models(id, name unique, provider, base_url, model_id, max_tokens,
  temperature, system_prompt text null, supports_reasoning bool, is_enabled bool,
  api_key_env text, extra jsonb, created_at, updated_at)`
  - **只存密钥的环境变量名**（如 `BR_DEEPSEEK_API_KEY`），绝不入库密钥（D 决议 + kickoff 红线）
  - 种子数据：`deepseek-v3`（对话/出题/评分）、`deepseek-r1`（reasoning 分流，D12）
- `better_resume/llm_gateway/registry.py`：读 `ai_models`（缓存 + 失效），`resolve(model_ref)`
- `better_resume/llm_gateway/adapters/openai_compat.py`：
  - `complete()`：httpx.AsyncClient + 超时；`response_schema` -> JSON 输出 + Pydantic 校验
  - `stream()`：SSE 逐帧解析 -> `ContentDelta | ReasoningDelta | Done | VendorMeta`
    （`reasoning_content` 五种位置兜底，照抄旧 `parseAiStreamChunk` 的经验但用 Python 重写）
  - 重试（仅 5xx/超时，指数退避，次数可配）、token 计量（`usage` 缺失则为 None）、
    失败分类三态（可重试/不可重试/供应商错误）
- `better_resume/llm_gateway/firewall.py`：最小注入防御纯函数（已知注入模式扫描 + system 加固），
  M1 只做「检出并标记/拒绝」，不做完整策略引擎
- `better_resume/http/models.py`：`GET /api/v1/models`（只返回 enabled；无密钥的模型标
  `configured: false`，诚实状态）
- 测试：`tests/llm_gateway/` —— 录制/回放样本（`tests/fixtures/llm/*.json`）+ `httpx.MockTransport`：
  content 流、reasoning 流、混合流、usage 计量、schema 校验失败->重试->降级、
  5xx 重试、4xx 不重试、超时分类、SSE 脏帧丢弃、firewall 命中/不命中

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway` | 全绿，**不需要任何真实 API key** |
| `GET /api/v1/models` | 返回 deepseek-v3 / deepseek-r1；未配置密钥时 `configured=false` |
| 回放样本 | 覆盖 DeepSeek 的 reasoning_content 与非 reasoning 两种响应 |

## 形态提议（待确认）

- 用 `httpx` 直连（不引 openai SDK）：少一个会变形的依赖，SSE 解析完全可控、可测（Q1）。
- `response_schema` 走 OpenAI 兼容的 `response_format=json_object` + Pydantic 校验 +
  重试（而不是 json_schema，兼容面更广）。
- raw 响应只记 `usage/latency/finish_reason` 到 structlog，不落原始 payload（Q8）。

## 实测记录（2026-09-13，用真实 key 跑通）

- 真实 stream：`ContentDelta` 与 `ReasoningDelta` 均正确归一，`Done` 收尾；
  真实 complete + `response_schema`：`parsed=Answer(answer='ok')`，usage 含 `reasoning_tokens`。
- **坑**：reasoning 与 content 共用 `max_tokens` 预算——`max_tokens=64` 时推理把预算吃光，
  content 为空 → 结构化输出必然失败（会被判成 LlmSchemaError）。注册表默认 2048/4096 没问题，
  但任何调用方都不要把 max_tokens 调得过小（已记入 T3/T9 注意事项）。
- **坑**：httpx 构造客户端时会急于解析 `NO_PROXY`，像 `::1`、`[::1]`、`<local>` 这类条目会抛
  `InvalidURL`（本机 WSL 环境就是如此）→ 适配器加了回退：`trust_env=False` + 告警日志。

## 不做

- 不做单飞/熔断/限流（M3）；不做 XingyunWorkflowAdapter（M5）；不做流式结构化输出。
