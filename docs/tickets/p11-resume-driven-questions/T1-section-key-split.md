# P11-T1 — 章节拆分：experience 拆成 work / internship

- Status: done（红绿已过，待用户验收）
- 依赖：无
- 缝：`better_resume.resume_parser.sections.split_sections`（纯函数，输入 TextBlock 列表）

> 阶段：P11（简历驱动的分类出题）。决策依据 `README.md` §1.4（Q1–Q19）与 `docs/DECISIONS.md` D23。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；测试只 mock 系统边界。

## 目标

「工作经历」与「实习经历」当前共用 `experience` 一个 key（首命中即止）→ 两者被抹平（README §1.2）。
拆成两个 canonical key：`work` / `internship`，让出题 prompt 与配比能区分它们（Q3）。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 含「实习经历」标题 | 该 section `key == "internship"` |
| 2 | 含「工作经历」标题 | 该 section `key == "work"` |
| 3 | 两份都有 | 得到 **两条不同 key** 的 section，顺序按版面自上而下 |
| 4 | 英文 `WORK EXPERIENCE` | `key == "work"`（大小写不敏感） |

## 需要同步改的既有断言（行为变更，非放宽）

- `tests/resume_parser/test_sections.py::test_english_headings_are_recognized_case_insensitively`：`["experience", "skills"]` → `["work", "skills"]`
- `tests/resume_parser/test_parser.py::test_parses_english_resume_into_context`：`"experience" in keys` → `"work" in keys`

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/resume_parser` | 全绿，且新用例先红后绿 |

## 不做

- 不改 heading 的关键词打分算法本身；不新增第四类；不动 `other` 兜底。
