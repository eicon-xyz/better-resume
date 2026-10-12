# P11-T7 — 出题配比：按简历算 + 显式类型覆盖

- Status: done（红绿已过，待用户验收）
- 依赖：T1、T8（`interview_type` 取值）
- 缝：`interview_engine.planning.plan_questions(context, count, interview_type)`（纯函数）

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q17：题量 5 —— 有实习 → 1 实习、有项目 → 2 项目、其余八股；**缺类则名额让给八股**。
Q8：默认由简历算，上传页可覆盖（覆盖语义见 T8）。配比以 prompt 指令传达，模型仍逐题给类别（T5），
报告展示**实际**分布。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 实习 + 项目 | `{internship: 1, project: 2, fundamentals: 2}` |
| 2 | 只有项目 | `{project: 2, fundamentals: 3}` |
| 3 | 什么都没有 | 全 `fundamentals`（5 道），且不抛错 |
| 4 | 数量守恒 | 任何输入下各类之和 == count（clamp 后） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_planning.py` | 全绿 |

## 不做

- 不做「按类强制分位」的硬编排（模型仍可自行判断）；不改默认题量 5。
