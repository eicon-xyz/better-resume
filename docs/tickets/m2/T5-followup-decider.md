# M2-T5 — 追问裁决纯函数 + 追问生成

- blocking：M2-T4
- 纪律：先写失败测试（红），再实现（绿）；**裁决是纯函数，穷举测试**

## 目标

§4.1.3 的 LiteFlow 规则链在 M2 落成一个纯函数（不引 LiteFlow）：
`decide_follow_up(...) -> FollowUpDecision{need_follow_up, reason_code, resolved_max_follow_up, terminated}`。

## 交付物

- `better_resume/interview_engine/follow_up.py`：
  - 判定顺序（软短路，与旧项目一致）：completedStateGuard（已完成 → 终止）→
    followUpLimitGuard（计数 ≥ 上限 → 不追问）→ aiSuggestionJudge（模型建议）→
    lowScoreJudge（分数 < 阈值）→ missingPointsJudge（要点缺失非空）→ finalize
    （无命中填 `NO_RULE_TRIGGER`）
  - `reason_code` 枚举：`AI_SUGGESTED / LOW_SCORE / MISSING_POINTS / FOLLOW_UP_LIMIT_REACHED /
    INTERVIEW_COMPLETED / NO_RULE_TRIGGER`
  - 规则版本号 + `fallback` 标记（引擎异常时 fail-open 不追问，记录 fallback=true）
- `better_resume/interview_engine/follow_up_service.py`：追问题生成（llm-gateway，
  `FollowUpQuestion{text}` schema），题号 `{topic_no}-F{index}`，写入 `interview_questions`，
  flow `evaluating → follow_up`
- `better_resume/http/interview.py`：答题响应里带 `next`（question/follow_up/finished）
- 测试：**判定表穷举**（5 个维度的组合 → 期望 reason_code）、每次调用不返回两个主动作、
  上限为 0 时不追问、fail-open 用例、题号渲染/解析（`3`、`3-F1`、`3-F2`）往返

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_follow_up.py` | 全绿（穷举用例数 ≥ 32） |
| 上限用例 | maxFollowUp=2 时第 3 次判定一定 `FOLLOW_UP_LIMIT_REACHED` |
| fail-open | 引擎抛异常时 `need_follow_up=false` 且 `fallback=true`（绝不静默编题） |

## 形态提议（待确认）

- 阈值默认：`low_score_threshold=60`、`max_follow_up=2`（旧项目经验值，见 Q4）。
- 决策结果**落库**到答案行（reason_code/rule_version），报告与调试都能复盘。

## 不做

- 不做规则热配置（M2 常量 + 参数注入即可）；不做多级追问链（只有一层 F{n}）。
