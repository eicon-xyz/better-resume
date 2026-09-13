# M1-T10 — M1 验收、文档与简历草稿

- blocking：M1-T1..T9

## 目标

把 §12.4 的 M1 验收落成可复核证据，并完成 D14 的「每 M 更新简历草稿」。

## 交付物

- `docs/tickets/m1/ACCEPTANCE.md`：逐条命令 + 输出摘要 + 文件路径 + **演示截图/录屏路径**
- `docs/tickets/m1/OPEN-QUESTIONS.md` 结论回填
- README 更新（当前状态 -> M1 完成；补「契约变更流程」）
- `docs/resume/M1-resume-draft.md`：把 llm-gateway（亮点④）与 SSE 链路写成可核验的条目；
  注明与旧简历「LLM 统一工厂层」「FastAPI + SSE + 15s 心跳」的承接关系
- GitHub：feature 分支 push + PR 链接（本机无 token，PR 由你在网页确认合并）
- CI 证据：run 链接 + 两个 job 的 step 摘要

## 验收

| 检查 | 期望 |
| --- | --- |
| §12.4 M1 验收三条 | 打字机 / reasoning 面板 / 历史回放 各有证据 |
| `uv run pytest` + `pnpm -C apps/web test` | 全绿（条数与 M0 对比有增长） |
| CI | 双 job 在 GitHub 上全绿 |
| 演示 | 有一段可给面试官看的真实对话记录（含 reasoning） |

## 不做

- 不把 M2（面试链路）的内容提前写进 M1 简历条目。
