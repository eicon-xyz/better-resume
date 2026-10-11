# P11-T3 — 语料加载器（缺文件 / 坏 JSON 大声失败）

- Status: done（红绿已过，待用户验收）
- 依赖：无（打包数据由语料整理任务产出）
- 缝：`better_resume.interview_engine.corpus.load_corpus(path=None)`

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

语料是随包发布的 JSON（`interview_engine/corpus/questions.json`），加载器用 `Path(__file__)` 定位、
**不依赖 cwd**（README §1.5）。Q19：**缺文件 / 坏 JSON = 发布缺陷，必须红**。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 正常文件 | 返回条目列表，字段完整（id/topic/question/source_url/fetched_at） |
| 2 | 文件不存在 | 抛 `CorpusError`，消息含路径 |
| 3 | JSON 损坏 | 抛 `CorpusError`，消息含路径 |
| 4 | 随包文件可载 | 默认路径（不传参）能载到 ≥100 条且 id 唯一 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/interview_engine/test_corpus.py` | 全绿 |
| `uv run python scripts/check_corpus.py` | 打包语料结构合规（条数/topic 配额/URL 去重） |

## 不做

- 不在加载期联网；不做热更新；不做语料版本迁移。
