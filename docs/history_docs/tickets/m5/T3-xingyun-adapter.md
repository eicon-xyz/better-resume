# M5-T3 — XingyunWorkflowAdapter（星云工作流 adapter）

- blocking：M4
- 纪律：先写失败测试（红），再实现（绿）；**用本地假星云服务端做契约测试，不 mock 内部模块**

## 目标

按 §4.1.8 实现第二个 `LlmGateway` 实现：把我们的 PromptBundle 调成星云工作流，
并把它的 SSE 输出归一成**与 OpenAICompatAdapter 完全相同**的 `StreamEvent` / `ChatResult`。

## 交付物

- `llm_gateway/adapters/xingyun.py`：
  - 鉴权：`Authorization: Bearer {apiKey}:{apiSecret}`（**只从环境变量读，绝不入库**）
  - 请求：`POST https://xingchen-api.xf-yun.com/workflow/v1/chat/completions`
    body = `{flow_id, uid, stream, chat_id?, history[], parameters{}}`（T4 负责映射内容）
  - 响应：SSE 行解析（`data: {...}` / `[DONE]`）→ `ContentDelta` / `ReasoningDelta` / `VendorMeta` / `Done`
  - 非流式路径：`complete()` 收集全部帧后按 `response_schema` 强校验 → `ChatResult(parsed=...) `
  - 错误归一：HTTP 4xx（凭据/flow 不存在，不可重试）→ `FailureKind.NON_RETRYABLE`；
    5xx/429/超时 → `RETRYABLE`；网络错误 → `RETRYABLE`（与现有 gateway 一致）
  - 注入防御：复用 `llm_gateway/firewall.py`（同一道防线，两个供应商）
  - 无 schema 时返回纯文本；有 schema 时校验失败先重试一次再抛 `LlmSchemaError`
- `llm_gateway/xingyun_factory.py`：`build_xingyun_gateway(binding, env) -> LlmGateway`
  （缺 apiKey/apiSecret/flow_id → `LlmConfigError`，不静默）
- 测试：`tests/llm_gateway/test_xingyun_adapter.py`（≥12 例，本地假服务端）

## 测试

| 用例 | 断言 |
| --- | --- |
| 请求形状 | 假服务端收到 flow_id/uid/stream=true/parameters（T4 的映射结果） |
| 鉴权头 | `Bearer apiKey:apiSecret`；密钥不出现在日志与响应里 |
| SSE 归一 | 多帧 → ContentDelta 序列 + Done(finish_reason) |
| reasoning 分流 | 带 reasoning 的帧进 ReasoningDelta（不混进 content） |
| 非流式 | 收集 + schema 校验通过 → `ChatResult.parsed` 是该 Pydantic 实例 |
| schema 失败重试 | 第一次返回非法 JSON → 重试一次 → 仍失败抛 `LlmSchemaError` |
| 4xx | 不可重试（`retryable=False`），错误信息含状态码与流程 id |
| 5xx/429 | 可重试；超时 → `LlmTimeoutError` |
| 注入防御 | 命中 firewall 的输入被拦（与 OpenAI 路径同断言） |
| 流中断 | 半截 SSE 后断开 → 明确错误，不返回半截结果 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway/test_xingyun_adapter.py` | 全绿 |
| 无凭据行为 | 工厂抛 `LlmConfigError`（失败要大声） |

## 不做

- 不做星云文件上传（我们的简历解析是本地确定性解析）；
- 不做工作流内的提示词管理（在云端，我们只控制输入映射与输出校验）；
- 不做星云侧的重试/兜底编排（那是 D04 自研编排的活）。

