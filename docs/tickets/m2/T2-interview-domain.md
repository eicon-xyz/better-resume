# M2-T2 — interview 领域模型 + 两层状态机 + 迁移

- blocking：M1
- 纪律：先写失败测试（红），再实现（绿）；状态转移表穷举测试

## 目标

把 §4.1.1 的**两套状态**落成 Postgres 行 + 表驱动状态机（旧项目是 Redis Hash + Lua CAS，
M2 按单体单机形态改为事务 + version 乐观锁，见 README §4.1）。

## 交付物

- 迁移 `0004_interview`：
  - `interview_sessions(id uuid pk, user_id, status, interview_type, resume_path, resume_sha256,
    resume_score, question_count, started_at, finished_at, created_at, updated_at)`
    约束：`status IN ('draft','resume_uploading','ready','in_progress','finished','abandoned')`；
    索引 `(user_id, status)`
  - `interview_questions(id, session_id fk, question_no text, topic_no int, follow_up_index int,
    text, focus_points jsonb, kind text, created_at)`；唯一 `(session_id, question_no)`
  - `interview_answers(id, session_id fk, question_no text, request_id text, answer text,
    score numeric, feedback text, missing_points jsonb, follow_up_needed bool,
    error_message text, created_at)`；**唯一 `(session_id, request_id)`**（幂等门禁）
  - `interview_flow_state(session_id pk fk, status text, current_index int, total_questions int,
    follow_up_count int, max_follow_up int, version int, updated_at)`
    约束：`status IN ('init','asking','evaluating','follow_up','completed')`
  - `interview_reports(session_id pk fk, payload jsonb, overall_score numeric, dimensions jsonb,
    summary text, created_at, updated_at)`
- `better_resume/interview_engine/session_fsm.py`：会话生命周期状态机
  （合法转移表 + 非法转移抛 `IllegalSessionTransition`；旧活跃会话被新会话取代 → abandoned）
- `better_resume/interview_engine/flow_fsm.py`：答题流程状态机（`INIT/ASKING/EVALUATING/
  FOLLOW_UP/COMPLETED`，同状态幂等放行）+ `mutate_flow_state`（version CAS，冲突重试 ≤3）
- `better_resume/interview_engine/orm.py` + `models.py`（Pydantic 视图）
- 测试（真库）：**转移表穷举**（每个 status × 每个目标 status）、非法转移报错、同状态幂等、
  CAS 冲突重试、会话取代（新会话把旧活跃会话置 abandoned）、唯一约束（重复 requestId）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run alembic upgrade head && uv run alembic check` | 无 drift |
| `uv run pytest -q tests/interview_engine/test_fsm.py` | 穷举用例全绿 |
| `uv run pytest -q tests/interview_engine/test_session_repo.py` | 真库用例全绿 |

## 形态提议（待确认）

- 题号用值对象 `QuestionNo(topic_no, follow_up_index)`，字符串形式 `3` / `3-F1`
  （对齐旧项目「主题号-F{n}」语义），解析/渲染都有单测。
- 报告存 `payload jsonb`（聚合快照）而不是每次现算：结束即冻结，回放稳定。

## 不做

- 不做 Redis 热态/分布式锁（M6）；不做冷热快照分层（单体单机不需要）。
