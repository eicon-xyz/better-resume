# P11-T10 — 降级路径：解析失败照开面试 + 响应明示

- Status: done（红绿已过，待用户验收）
- 依赖：T7（全八股兜底）
- 缝：`interview_engine.question_service.generate` → `http.interview.QuestionBatchView`

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q18 / Q4：简历没解析出东西时**照常开面试**（纯 LLM 通用八股），响应带 `degraded` + 原因，前端明示。
Q2.2：语料没匹配上也降级，并明示「本次未使用语料」。Q19：缺文件/坏 JSON 仍是硬失败，不走降级。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 解析失败照开 | 解析抛 `ResumeParseError` → 仍出 5 道题，`degraded=true`，reason 含原因码 |
| 2 | 正常不谎报 | 解析正常 → `degraded=false`，reason 为 null |
| 3 | 语料没匹配 | 有解析但技能全不匹配语料 → `degraded=true` 且原因区别于解析失败 |
| 4 | 坏语料不降级 | 语料文件损坏 → **硬失败**（不是 degraded） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_interview_api.py tests/interview_engine/test_question_service.py` | 全绿 |

## 不做

- 不做 OCR；不拒绝重传；不为降级场次单独建模型。
