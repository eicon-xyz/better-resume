# P11-T8 — interview_type 改受控枚举

- Status: done（红绿已过，待用户验收）
- 依赖：无（T7 消费它的取值）
- 缝：`interview_engine.categories.InterviewType` / `http.interview.InterviewSessionCreateRequest` / 前端上传页

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q15：`interview_sessions.interview_type` 从自由文本改**受控枚举**（迁移 + 前端下拉）；
**非法值回退 `auto`**（不是 422 —— 旧前端/脏数据不该把面试拦死）。

取值与覆盖语义（**spec 未枚举取值，实施时定的，见 ACCEPTANCE 的偏差清单**）：

| 值 | 含义 | 配比 |
| --- | --- | --- |
| `auto` | 默认：按简历算 | 见 T7 |
| `fundamentals` | 只要八股 | 5 八股 |
| `project` | 项目为主 | 3 项目 + 2 八股（不足则让位八股） |
| `internship` | 实习为主 | 3 实习 + 2 八股（不足则让位八股） |

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 非法回退 | `POST /sessions {interview_type:"banana"}` → 201 且存回 `auto` |
| 2 | 显式生效 | `{interview_type:"project"}` → 存回 `project` |
| 3 | 缺省 | 不传 → `auto` |
| 4 | 迁移 | 旧库里的自由文本值被归一成枚举成员；`alembic check` 无差异 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_interview_api.py tests/interview_engine` | 全绿 |
| `pnpm -C apps/web test --run` | 全绿（下拉渲染 + 提交值） |

## 不做

- 不做每类自定义题量的高级面板；不做历史值的语义还原（无法还原，一律 auto）。
