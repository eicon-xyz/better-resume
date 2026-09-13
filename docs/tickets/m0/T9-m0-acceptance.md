# T9 — M0 验收证据汇总

- blocking：T1–T8

## 目标

把 kickoff 的 6 条完成标准逐条落成可复核的证据，做到「你没有需要手动补的步骤」。

## 交付物

- `docs/tickets/m0/ACCEPTANCE.md`：逐条标准 -> 命令 -> 退出码 -> 输出摘要 -> 文件路径
  （结构 / compose healthy / ruff+pytest+alembic / eslint+tsc+vitest / CI workflow /
  六模块包外导入 + 占位测试）
- `docs/tickets/m0/OPEN-QUESTIONS.md` 的结论回填（拍板后逐条记录）
- README「当前状态」更新为 M0 完成态

## 验收

| 检查 | 期望 |
| --- | --- |
| kickoff 完成标准 6 条 | 每条都有命令 + 输出证据 |
| `git log --oneline` | 小步提交序列，每条 message 说 WHAT |
| 手动补步骤清单 | 仅剩「确认决议 / 给 GitHub remote」两类 |

## 与 D14 的关系

D14 硬规则「每个 M 结束更新一次简历草稿」需要你的简历草稿文件位置与口径；
M0 是否包含该动作见 OPEN-QUESTIONS D-F。

## 不做

- 不改 docs/DECISIONS.md 与 docs/ai-meeting-architecture-analysis.md（冲突只列不改）。
