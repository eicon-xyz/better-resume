# P11-T6 — 追问继承主问题类别

- Status: done（红绿已过，待用户验收）
- 依赖：T5
- 缝：`interview_engine.follow_up_service`（创建追问行处）

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q12：追问**继承主问题**的类别（零成本；顺带得到「八股深度 / 项目深度」）。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 继承 | 主问题 `category=project` → 其追问行 `category=project` |
| 2 | 不猜 | 主问题为 NULL（历史行）→ 追问也为 NULL，不硬塞 `fundamentals` |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_follow_up_flow.py` | 全绿 |

## 不做

- 不让模型单独判追问类别；不加新字段。
