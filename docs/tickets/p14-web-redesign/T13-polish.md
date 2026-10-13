# P14-T13 — 报告页收尾小修：pending 等待态 / 回放组头去重 / 空态卡宽度

- Status: ready-for-agent
- Blocked by: 无
- 唯一写入路径：`apps/web/src/pages/InterviewReportPage.tsx`、`apps/web/src/pages/InterviewReportPage.module.css`、`apps/web/src/pages/InterviewReportPage.test.tsx`、`apps/web/src/components/Empty.tsx`、`apps/web/src/components/Empty.module.css`、本票与 `T13-EVIDENCE.md`

> 依据 README §1.4 报告页线框 / §1.5 视觉语言、`T4-EVIDENCE.md`（报告页现状）、D24 / D25。
> 纪律：不改业务逻辑 / 数据流 / REST 契约 / 路由；不碰 `src/api`、`src/audio`、`src/stream`、`src/chat` 语义层；不新增依赖；不 commit。

## 目标

1. **报告 pending 态**：`report.summary_pending === true` 时，「改进建议」卡显示等待态「总结生成中…」（Spinner + 文案，轻量）；`summary` 为空且非 pending 时才显示既有降级文案「未生成总结（模型不可用或未配置），分数与逐题记录不受影响。」——该文案一字不改。
2. **逐题回放组头去重**：组头由「第 N 题 · <题面>」改为「序号徽记（数字）+ 题面原文」；折叠开合与「全部展开 / 全部收起」语义不变。
3. **空态卡宽度**：`Empty` 内容宽度上限约 480px 并居中，字号层级微调；只调宽度与层级，不重设计。

## 不做

- 不动业务逻辑、数据流、TanStack Query / zustand 用法、REST 契约、路由表；不碰 `src/api`、`src/audio`、`src/stream`、`src/chat`。
- 不改既有行为单测的意图；只有受组头文案影响的「文本 / 角色位置」类断言随实现同步，逐条记录进 `T13-EVIDENCE.md`。
- 不新增依赖、不新增 token、不新增 `allow:` 白名单；不动 README、T1–T12 票与既有 EVIDENCE；不 commit。

## 验收

| 命令 | 期望 |
| --- | --- |
| `python3 scripts/check_web_style_guards.py` | exit 0，末行 `check_web_style_guards: ok` |
| `grep -rn 'allow:' apps/web/src \| wc -l` | 41（不增） |
| `pnpm -C apps/web test --run` | 通过例数 ≥210（只增不减） |
| `pnpm -C apps/web typecheck`、`pnpm -C apps/web lint` | exit 0 |
| 变异证明 `bash scripts/verify_mutation.sh` | 删 pending 判定 → pending 单测红 → 恢复绿（sha256 / cmp 复核） |

行为单测：pending 态新增 2 例（README §4.1「带逻辑的新组件行为单测」缝）；空态纯样式不写测试（守卫兜底）。
