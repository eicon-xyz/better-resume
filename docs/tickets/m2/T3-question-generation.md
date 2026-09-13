# M2-T3 — 出题链路（LLM + schema 强校验 + 落库 + 幂等）

- blocking：M2-T1 M2-T2
- 纪律：先写失败测试（红），再实现（绿）；LLM 只 mock HTTP 边界

## 目标

`InterviewEngine.start()` 的第一段：把 `ResumeContext` 变成一组有考察点的题目，
落库成 `interview_questions`，并把会话推到 `ready`（§7.3 的第一阶段）。

## 交付物

- `better_resume/interview_engine/prompts.py`：出题提示词模板（中英各一套）+
  `response_schema`：`QuestionBatch{questions: list[GeneratedQuestion{topic, focus_points[], text}],
  resume_score: float, suggestions: list[str]}`
- `better_resume/interview_engine/question_service.py`：
  - 幂等：同 `(session, request_id)` 重复调用直接返回已生成的题目（唯一约束兜底）
  - 走 `AiResilience.run(Stage.EXTRACTION, key, ...)`（M2 直通实现）→ llm-gateway `complete()`
  - schema 校验失败 → 由网关重试 → 仍失败则 `ResumeParseError`（**提示用户重传，不编题**）
  - 成功后：写 `interview_questions` + `interview_flow_state(total_questions, status=init)` +
    会话 `resume_score`/question_count + `status=ready`（同一事务）
- `better_resume/http/interview.py`：`POST /api/v1/interview/sessions`（建会话 DRAFT）、
  `POST /api/v1/interview/sessions/{id}/questions`（上传简历 + 出题，multipart）
- 测试（mock 网关 + 真库）：schema 不合规时不落库不留半截状态、重复投递不重复出题、
  出题数与 focus_points 落库一致、异常路径会话回到 `draft`（可重试）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_question_service.py` | 全绿（含失败回滚用例） |
| 真实冒烟（本地带 key） | 一份真实简历 → N 道题且每题带 focus_points |
| 事务性 | 网关失败时 `interview_questions` 与 `flow_state` 均为空 |

## 形态提议（待确认）

- 题目数量由请求参数控制（默认 5），上限 10（防止一次把 token 预算炸掉）。
- 提示词放代码（可测试、可 diff），模型级 `system_prompt` 仍来自注册表；两者拼接顺序固定。

## 不做

- 不做题库/去重缓存；不做多轮出题迭代（一次生成一批）。
