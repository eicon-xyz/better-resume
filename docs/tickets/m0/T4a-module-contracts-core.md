# T4a — 模块契约：conversation / llm-gateway / ai-resilience

- blocking：T2

## 目标

按 §12.2 的签名级设计落三个模块：Protocol + Pydantic 类型 + 可导入占位实现，
包外可导入，附合约冒烟测试（M0 不做实现）。

## 交付物

- `better_resume/conversation/`：`SessionRef`（kind 属于 chat|interview，M0 不含 agent，见 OPEN-QUESTIONS D-H）、
  `Message`、`ConversationStore` Protocol（`append` / `history` / `require_owner`）
- `better_resume/llm_gateway/`：`ChatRequest` / `ChatResult` / `Message` /
  `StreamEvent = ContentDelta | ReasoningDelta | Done | VendorMeta`、`LlmGateway` Protocol
  （`complete` / `stream`）
- `better_resume/ai_resilience/`：`Stage` 枚举（extraction/evaluation/followup，demeanor 随 D09 裁剪）、
  `AiResilience` Protocol（`run(stage, key, fn)`）
- 每个模块 `placeholder.py`：可实例化的占位实现（方法体 `raise NotImplementedError`，类型完整）
- 测试：`tests/contracts/test_*_contract.py` —— 包外导入 + Protocol 结构/签名断言 + 占位实现可实例化

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python -c "import better_resume.conversation, better_resume.llm_gateway, better_resume.ai_resilience"` | exit 0 |
| `uv run pytest -q tests/contracts` | 全绿 |
| 人工核对 | 签名与 §12.2 逐条一致（差异写进 T9 证据） |

## 形态提议（待确认）

- 类型放 `models.py`、Protocol 放 `protocols.py`、占位实现放 `placeholder.py`，`__init__.py` 只做导出。
- `Stage` 不含 `demeanor`（D09 砍神态分析）——与 §12.2 注释有出入，按 DECISIONS 优先。

## 不做

- 不接真实 LLM、不写单飞/熔断实现、不写 SQLAlchemy 模型（M1/M3）。
