# M5-T4 — 场景映射层：PromptBundle ↔ 星云参数、输出 → Pydantic

- blocking：M5-T3
- 纪律：先写失败测试（红），再实现（绿）；**显式映射表，禁止别名回退猜测**

## 目标

星云工作流是黑盒：它的输入是 `parameters`，输出是自由文本/JSON。本票定义**唯一**的映射规则，
让"同一场景的两种供应商"在语义上对齐（同样的输入、同样的输出 schema）。

## 交付物

- `llm_gateway/scene_mapping.py`：
  - `to_xingyun_payload(scene, request: ChatRequest, *, flow_id, uid) -> dict`：
    把系统提示词/用户内容/结构化要求映射成 `history` + `parameters`（每个场景一段显式映射，
    写在一张表里，便于评审时逐条对照）
  - `from_xingyun_result(scene, text, schema) -> BaseModel`：**只认 schema 的字段名**，
    多余字段忽略、缺失字段报 `LlmSchemaError`；**不做别名回退**
  - 反向：`to_openai_messages(...)` 复用现有行为（保证两条路径输入一致）
- 场景对齐表（文档 + 代码注释，逐场景列出"传什么 / 期望什么字段"）：
  | 场景 | 传给星云 | 期望输出（Pydantic） |
  | --- | --- | --- |
  | question_extraction | 简历上下文 + 题量 + 语言 | `QuestionBatch{questions[], resume_score}` |
  | answer_evaluation | 题干 + 要点 + 答案 | `ScoreResult{score, feedback, missing_points, follow_up_needed}` |
  | follow_up | 题干 + 答案 + 缺失要点 | `FollowUpQuestion{text}` |
  | report_summary | 分数 + 维度 + 缺失要点 | `ReportSummary{summary}` |
  | chat | 历史消息 + 本轮内容 | 纯文本流（无 schema） |
- 测试：`tests/llm_gateway/test_scene_mapping.py`（≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 五个场景的输入映射 | 各有一条 golden payload（字段与顺序稳定，快照测试） |
| 两条路径一致 | 同场景下传给星云的语义内容与 OpenAI messages 一致（同一份 PromptBundle） |
| 输出严格解析 | 正确字段 → 该 Pydantic 实例；字段改名 → `LlmSchemaError` |
| 多余字段 | 忽略但不报错（宽容输入，严格必需字段） |
| 缺失必需字段 | 明确报错（含场景名与缺失字段名） |
| 不做别名回退 | `sugest`/`total_score` 之类的旧别名**不会**被接受（反例用例，锁死这条纪律） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway/test_scene_mapping.py` | 全绿 |
| 反例校验 | 删掉"严格必需字段"检查后至少 3 例转红 |

## 不做

- 不做提示词翻译（云端有自己的提示词，我们只保证输入语义与输出契约）；
- 不做多个星云工作流版本的兼容层（一个场景一个 flow_id，切换即换绑定）。

