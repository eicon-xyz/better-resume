# P11-T4 — 语料过滤：按简历技能取 top-N

- Status: done（红绿已过，待用户验收）
- 依赖：T3
- 缝：`better_resume.interview_engine.corpus.filter_corpus(entries, skills, limit)`

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

Q14：按简历 skills 标签过滤，取 top-N（默认 20–30，可配）；**不引向量检索**（D03）。
匹配规则要避免「Java 命中 JavaScript」这类子串误配：技能串切词后与 topic/别名集做**词级**比较。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 命中 | 技能含 Redis → 结果里必有 topic=Redis 的题 |
| 2 | 不误配 | 技能只有 Java → 结果里**没有** topic=JavaScript 的题 |
| 3 | 无匹配 | 技能全不匹配 → 返回空列表，**不抛错**（Q19 降级而非失败） |
| 4 | 上限 | limit 生效（结果长度 ≤ limit），且顺序稳定（同输入同输出） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_corpus.py` | 全绿 |

## 不做

- 不做排序打分/相关度模型（纯过滤 + 稳定顺序）；不做运行期联网补充。
