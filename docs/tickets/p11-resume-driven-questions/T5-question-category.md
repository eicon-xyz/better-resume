# P11-T5 — 题目类别：契约字段 + 枚举校验 + 规则回退

- Status: done（红绿已过，待用户验收）
- 依赖：T1（规则回退要认项目/实习段）
- 缝：`interview_engine.prompts.GeneratedQuestion` / `interview_engine.categories.decide_category` / `interview_engine.question_service._persist`

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q10 / D23：模型在每道题上给类别（`fundamentals` / `project` / `internship`），引擎用枚举校验；
**非法或缺失回退到规则推断**。落库到 `interview_questions.category`（可空，历史行 NULL=未分类）。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | schema 容忍 | 模型返回合法枚举 → 字段就是该枚举；非法字符串/缺失 → 字段为 `None`（**不炸整批**） |
| 2 | 规则回退 | 题干引用项目名 → `project`；引用实习段 → `internship`；都不沾 → `fundamentals` |
| 3 | 落库 | 生成的每道 main 题入库后 `category` 非空且等于「模型值或回退值」 |
| 4 | 迁移 | 迁移后旧行 `category` 为 NULL，新列可查询（`alembic check` 不报差异） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine tests/test_interview_api.py` | 全绿 |
| `uv run alembic upgrade head && uv run alembic check` | 无差异 |

## 不做

- 不为历史行回填类别（NULL 就是「未分类」）；不做类 × 四维矩阵。
