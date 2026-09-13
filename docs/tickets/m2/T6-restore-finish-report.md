# M2-T6 — 恢复 / 结束 / 报告聚合（雷达维度 + 逐题回放）

- blocking：M2-T5
- 纪律：先写失败测试（红），再实现（绿）；报告是**确定聚合**，不交给 LLM 编

## 目标

§7.3 的后半段：断线恢复（`restore`）、收口（`finish`）、报告（`report`）。

## 交付物

- `better_resume/interview_engine/restore_service.py`：`GET /api/v1/interview/sessions/{id}/restore`
  → `SessionView{status, question_no, total, answered, current_question, last_result, flow_status}`
  - **从数据库派生**（M2 无 Redis 热态）：答案行 + 题目行 + flow_state 三者一致即可恢复；
    若 flow 行缺失 → 由答案行派生并回写（记 `derived=true`，对齐旧项目 RehydrateService 精神）
- `better_resume/interview_engine/finish_service.py`：`POST …/finish`（幂等）
  - 事务内：聚合分数（各题 score 平均 + 缺失要点汇总）→ 生成 `interview_reports.payload` →
    会话 `finished` + `finished_at`；重复调用直接返回既有报告
- `better_resume/interview_engine/report_service.py`：`GET …/report`
  - `dimensions`：四维雷达（默认 准确性 / 深度 / 表达 / 结构性；见 Q3）
  - `turns`：逐题回放（题目 + 答案 + 分数 + 反馈 + 是否追问）
  - `summary`：允许 LLM 写一段总结（失败则留空，报告仍可用 → 反幻觉分工）
- 测试（mock 网关 + 真库）：restore 三种入口态（asking/follow_up/completed）、
  flow 行被删后 restore 能派生并回写、finish 幂等（第二次返回同一 payload）、
  报告维度与逐题数据与答案行一致、LLM 总结失败不影响报告

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_restore_report.py` | 全绿 |
| 恢复用例 | 删掉 `interview_flow_state` 行后 restore 仍能给出正确题号与状态 |
| 幂等用例 | finish 调用两次，报告 payload 完全一致且只生成一次 |
| 反幻觉 | 无 key/网关卡死时 finish 仍成功、summary 为空 |

## 形态提议（待确认）

- 报告 payload 冻结在 `interview_reports`（结束即快照），后续改算法不影响历史报告。
- 雷达维度由 `focus_points` 命中率 + 分数聚合推导，不让 LLM 打分（见 Q3）。

## 不做

- 不做 PDF 报告导出；不做对比多次面试的趋势图（M2 只做单次报告）。
