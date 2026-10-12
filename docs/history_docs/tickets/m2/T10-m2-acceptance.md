# M2-T10 — M2 验收、文档与简历草稿

- blocking：M2-T1..T9

## 目标

把 §12.4 的 M2 验收落成可复核证据，并完成 D14 的「每 M 更新简历草稿」。

## 交付物

- `docs/tickets/m2/ACCEPTANCE.md`：逐条命令 + 输出摘要 + 文件路径 +
  **一段完整的真实面试记录**（题目/答案/分数/追问/报告截图路径）
- `docs/tickets/m2/OPEN-QUESTIONS.md` 结论回填
- README 更新（M2 完成状态 + 面试链路说明）
- `docs/resume/M2-resume-draft.md`：把 interview-engine（亮点②）与 resume-parser（亮点⑤）
  写成可核验条目，对齐旧简历「五阶段 Prompt Pipeline」「Agent 追问不编造数据」
- GitHub：feature 分支 `m2/interview-engine` → PR（用 gh 创建）→ CI 绿 → 合并
- CI 证据：跑一次 `gh run view` 的双 job 摘要

## 验收

| 检查 | 期望 |
| --- | --- |
| §12.4 M2 验收 | 上传简历 → 完整面试 → 雷达图报告，三条各有证据 |
| 后端 / 前端测试 | 全绿且条数较 M1 有增长（M1: 94 / 65） |
| 真实链路 | 一次 5 题面试（含追问）端到端跑通，报告可截图 |
| CI | PR 与 main 上的双 job 全绿 |

## 不做

- 不把 M3（韧性）与 M4（语音）的内容提前写进 M2 简历条目。
