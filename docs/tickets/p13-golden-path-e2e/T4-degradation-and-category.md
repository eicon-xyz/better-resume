# P13-T4 — 降级路径与类别一致性的断言

- Status: ready-for-agent
- Blocked by: T2
- 唯一写入路径：`apps/api/scripts/interview_smoke.py`（追加场景）与所需 fixture

> 阶段：P13（假模型驱动的黄金路径 E2E）。依据 `README.md` §1.2 现状表与 §1.3。
> Q3 已定（同 T2）：AI 交脚本与单元级断言，**端到端读数由用户在宿主机跑并回填**；验收包里两类读数分开列。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；只 mock 系统边界；断言走公开行为。
## 目标

把 `docs/MANUAL-TESTING.md` §1.5 第 10–13 项的**语义层**变成断言：两类降级 + 类别落库 + 按类聚合一致性。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 无文本层 PDF | 不报错；仍出 5 题；`interview_sessions.resume_warnings` 落库；降级原因在响应/报告里明示 |
| 2 | 技能与语料无关的简历 | 仍出题；降级原因为「未匹配到八股语料」 |
| 3 | 类别落库与继承 | 每题 `interview_questions.category` ∈ 三枚举；追问的 `category` == 主问题的 |
| 4 | 按类聚合一致 | `category_breakdown` 的题数与逐题 `category` 一致；某类 < 2 题 → 不出分数 + 「样本不足」 |

fixture 注意：合成 PDF 的 **CJK 分隔符会被字体抹掉**（`docs/tickets/p11-resume-driven-questions/PROBLEMS.md` §2 记过这个坑）——
需要真实技能串时用 ASCII 逗号分隔的那份构造方式。

## 红线

- 查库用既有模式：`docker compose exec -T postgres psql -v ON_ERROR_STOP=1`（见 `scripts/compose_smoke.sh:110`）。
- 每次跑用**唯一 run id**，不依赖上一次的残留数据；跑完的共享状态自己还原。
- 断言的**预期来自契约与 D23**，不是「系统返回了什么」——`CODING_STANDARDS.md` §6 第 1 条。
- 只写 T2 那个脚本与 fixture；不动引擎与迁移。

## 验收

| 命令 | 期望 |
| --- | --- |
| 断言模式跑四个场景 | 逐条 PASS；证据落 `var/evidence/<ts>-e2e/` |
| 故意改坏一条断言 | 非 0 退出（贴原始输出） |
| `uv run pytest -q --junitxml=/tmp/x.xml` | 全绿、0 skipped |

## 不做

- 不断言「题目整体偏项目」——那依赖真模型是否理会配比提示，假供应商测不出（`README.md` §1.4）。
- 不做报告页的视觉断言（渲染层留给人）。
