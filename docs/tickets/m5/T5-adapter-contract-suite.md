# M5-T5 — 双 adapter 契约测试套件（一套用例，两个实现）

- blocking：M5-T3
- 纪律：先写失败测试（红），再实现（绿）；这是 M5 的"真接缝"证据票

## 目标

用**同一套契约用例**驱动 `OpenAICompatAdapter` 与 `XingyunWorkflowAdapter`：任何一条行为不一致，
测试就红。这是"两个 adapter 是同一个接缝的两个实现"这一说法的机器可验证版本。

## 交付物

- `tests/llm_gateway/adapter_contract.py`：参数化的契约用例集（pytest parametrize over adapter fixtures）：
  - `complete()` 返回 `ChatResult`，带 `content`/`model`；有 schema 时 `parsed` 是对应实例
  - `stream()` 产出 `ContentDelta` 序列，以 `Done` 结束；reasoning 走独立事件
  - schema 失败：重试一次 → 仍失败抛 `LlmSchemaError`（不可重试）
  - 可重试/不可重试错误分类一致；超时一致
  - 注入防御一致
  - 取消（客户端断开）：流被关闭且不产生半截 `ChatResult`
- 两个 fixture：`openai_compat_gateway`（本地假 OpenAI 兼容服务端）、
  `xingyun_gateway`（本地假星云服务端）
- **录制样本**：`tests/fixtures/llm/xingyun_*.sse` —— 按 §4.1.8/§4.3 描述的形状手写的最小样本，
  文件头注释写明"形状来自架构文档描述，真机样本待 T10 替换"
- 测试：契约套件本身即测试（≥12 例 ×2 adapter）

## 测试（契约条目，两个 adapter 都必须满足）

| # | 契约 | 断言 |
| --- | --- | --- |
| 1 | 非流式返回 | `ChatResult.content` 非空、`model` 正确 |
| 2 | 结构化输出 | `parsed` 是 schema 实例，字段值正确 |
| 3 | 流式序列 | 至少一个 `ContentDelta` 且以 `Done` 收尾 |
| 4 | reasoning 分流 | reasoning 不出现在 content 里 |
| 5 | schema 失败 | 重试一次 → `LlmSchemaError`（`retryable=False`） |
| 6 | 5xx/429 | 可重试错误（`retryable=True`） |
| 7 | 4xx 凭据/资源错误 | 不可重试 |
| 8 | 超时 | `LlmTimeoutError`（可重试） |
| 9 | 注入防御 | 与 firewall 单测同一断言 |
| 10 | 取消 | 无 `ChatResult`、无残留任务 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway/test_adapter_contract.py` | 两个 adapter 各 10 条全绿 |
| 反例校验 | 故意让星云 adapter 的 reasoning 混进 content → 契约用例红（证明套件有鉴别力） |

## 不做

- 不做真实供应商的 CI 调用（那是 T10 的活）；CI 里两个 adapter 都打本地假服务端。

