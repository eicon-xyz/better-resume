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

## 实测记录与偏差（2026-09-13）

- **雷达四维改名 + 公式确定化**（对 Q3 的细化；理由：目前只有分数/缺失要点两类信号，
  没有表达层的音频或文本特征，硬凑"表达/结构性"会变成假指标）：

  | key | 名称 | 公式 |
  | --- | --- | --- |
  | accuracy | 准确性 | 主问题得分均值 |
  | depth | 深度 | 追问得分均值；**未触发追问时沿用准确性** |
  | coverage | 要点覆盖 | `100 - 12 × 每题平均缺失要点数`（下限 0） |
  | completeness | 完成度 | `100 × 已答主问题 / 主问题总数` |

  想换成"表达/结构性"，我把公式替换掉即可（改动只在一个纯函数里）。
- **报告是冻结快照**：`finish` 一次性写 `interview_reports.payload`，重复调用返回同一份
  （测试断言 payload 完全相同、只落一行）。
- **LLM 总结是可选项**：失败/无 key 时 `summary=null`、`llm_summary_used=false`，分数照常。
- **恢复的派生路径**：flow 行被删时，从「题目 + 已答答案」重算当前题号与状态并**回写**，
  返回 `derived=true`（对齐旧项目 EXACT/DERIVED 置信度思想）。

## 不做

- 不做 PDF 报告导出；不做对比多次面试的趋势图（M2 只做单次报告）。
