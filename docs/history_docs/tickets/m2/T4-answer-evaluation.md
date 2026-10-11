# M2-T4 — 答题/评分链路（幂等门禁 + 题级锁 + 回滚）

- blocking：M2-T3
- 纪律：先写失败测试（红），再实现（绿）

## 目标

§4.1.2 的八步流水线，砍掉 Redis 相关件后落到 Postgres + 进程内锁：
校验归属与状态 → requestId 归一 → 幂等门禁 → 载题 → 题级锁 → 锁后复验 → 评分 →
推进/回滚。

## 交付物

- `better_resume/interview_engine/answer_service.py`：
  - 幂等：`(session_id, request_id)` 唯一；重复请求**回放**上次结果（不重复计费）
  - 题级锁：`asyncio.Lock` per `(session_id, question_no)`（进程内）+ 锁后复验问题状态
  - 评分：`ScoreResult{score, feedback, missing_points[], follow_up_needed}` schema 强校验
  - flow 推进：`asking → evaluating → (asking | follow_up | completed)`，非法转移回滚答案行
  - 评分失败：**不吞**——写 `error_message`，flow 回到 `asking`（可重答），旧值不污染
- `better_resume/http/interview.py`：`POST /api/v1/interview/sessions/{id}/answers`
- 测试（mock 网关 + 真库）：
  - 重复 requestId 回放（网关只被调用一次）
  - 并发同一题（`asyncio.gather`）只评一次、只有一个答案行
  - 评分失败 → flow 回 `asking`、答案行标 error、可重答成功
  - 非法转移（已完成会话再答题）→ 409/409 语义
  - 状态机与答案行的原子性（事务回滚后两边都不变）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_answer_service.py` | 全绿 |
| 并发用例 | 20 个并发同题请求 → 网关调用 1 次、答案行 1 条 |
| 回滚用例 | 让网关抛超时 → `flow_state.status == asking` 且无非法 score |

## 形态提议（待确认）

- 幂等回放直接返回上次的 `ScoreResult`（含 next 决策），前端无感重试。
- 题级锁用 `dict[(session, question_no)] -> asyncio.Lock` + 弱引用清理；M6 换 Redis 锁时只改这一处。

## 不做

- 不做「答题草稿暂存」；不做部分评分/流式评分。
