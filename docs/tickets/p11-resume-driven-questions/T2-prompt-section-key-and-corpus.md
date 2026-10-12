# P11-T2 — prompt 带 section key ＋ 注入八股语料

- Status: done（红绿已过，待用户验收）
- 依赖：T1（key 拆分）、T3/T4（语料）
- 缝：`interview_engine.prompts.render_context` / `build_messages`

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

现状：`render_context` 只输出 `[标题]`，模型看不到段落类型（README §1.2）；
本票让它输出 canonical key，并把过滤后的八股语料作为**参考题**拼进 user 消息（Q14）。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 段落类型可见 | 实习段的渲染行含 `internship`（key 字面量） |
| 2 | 语料进 prompt | 传入语料条目时，user 消息含该题题干与其 topic |
| 3 | 无语料不崩 | 语料为空/None 时消息里没有语料小节，其余内容不变 |

> 说明：§4.1 的 T2 只写了「带 key」。语料注入是 §1.3-2 与交付物里的要求，
> 本票补上第 2/3 条断言，避免「注入」变成没有测试钉住的声称。

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_prompts.py` | 全绿 |

## 不做

- 不在 prompt 里做向量检索、不联网；语料只做参考题，不做机械抽题。
