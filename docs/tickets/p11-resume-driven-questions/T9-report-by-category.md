# P11-T9 — 报告按类给分（分数 / 题数 / 评语）

- Status: done（红绿已过，待用户验收）
- 依赖：T5、T6
- 缝：`interview_engine.report_service._aggregate`（payload.categories）+ `http.interview.InterviewReportView` + 报告页

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q7：四维雷达**不动**，另开一节按类给分。Q16：每类给**分数 + 题数 + 一句评语**；
某类 **< 2 题不出分数**，写「样本不足」。Q13：报告里列清本场类别与配比（三类都列，含 0 题的）。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 聚合 | 各类 `count` == 该类别名下有分数的 turn 数（含追问）；`score` == 这些分数的均值（1 位小数） |
| 2 | 样本不足 | 某类只有 1 题 → `score is None` 且 `comment == "样本不足"` |
| 3 | 零题类别 | 本场没有的类别也出现在列表里，count=0、score=None、样本不足 |
| 4 | 冻结不重算 | `/report` 与 `finish` 的 categories 一致（同一份 payload） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_interview_report_api.py tests/interview_engine/test_report_suggestions.py` | 全绿 |
| `bash scripts/verify.sh --layer contract` | `openapi.json` 与 `schema.d.ts` 同步（契约三件套） |

## 不做

- 不做类 × 四维矩阵；不让 LLM 算这节的分数或评语（确定性聚合）。
