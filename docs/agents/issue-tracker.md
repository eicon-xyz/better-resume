# Issue tracker: 本地 Markdown（映射到 `docs/tickets/<stage>/`）

本仓库的工作项——**spec 与票据**——以 markdown 文件形式提交进 git，放在 `docs/tickets/<stage>/`。
沿用仓库既有的「阶段提案制」命名，**不另起 `.scratch/`**。

## 目录约定

- 一个阶段 = 一个 feature = 一个目录：`docs/tickets/<stage>/`，`<stage>` 形如 `p4-xxx`（小写 + 连字符）。
- **spec**：`docs/tickets/<stage>/README.md`——即本仓库的「阶段提案」，固定六段：范围 / 不做 / 交付物 / 测试与验收口径 / 预估 / 需要用户决定的问题。
- **票据**：一个票据一个文件，`docs/tickets/<stage>/T<N>-<slug>.md`，`N` 从 1 起按依赖顺序编号（blockers 在前）。
  **绝不把多个票据写进同一个文件**；沿用既有的 `T<N>-` 前缀，不用 `issues/NN-`。
- **阻塞**：票据文件靠近顶部的 `Blocked by: T1, T3` 行；它列出的票据全部完成后，该票据才可开工。
- **状态**：票据文件靠近顶部的 `Status: <字符串>` 行，取值见 `triage-labels.md`。没有 `Status:` 行 = 未分类。
- **讨论**：追加到文件底部的 `## Comments` 标题下。
- **证据**（阶段收口）：`ACCEPTANCE.md`、`<ticket>-EVIDENCE.md`、`PROBLEMS.md`（难题即时记）。

## 当某个技能说「发布到 issue tracker」

- 发布 **spec** → 写/更新 `docs/tickets/<stage>/README.md`。
- 发布 **票据** → 写 `docs/tickets/<stage>/T<N>-<slug>.md`。

## 当某个技能说「取回相关票据」

直接读那个路径的文件。用户通常会直接给出阶段名或路径。

## 人工闸门（本仓库特有，**优先于技能默认行为**）

「阶段提案制」永久生效：**spec 必须先经用户明确确认才动工**。因此：

- `/to-spec`、`/to-tickets` 发布产物时，`ready-for-agent` 在本仓库的含义是
  **「已完整规格化、待用户点头」**，**不是**「可以立刻开工」。
- 用户明确点头（通常一句话）之后，才进入 `/implement`。
- 验收同样由用户完成：AI 不自行宣布完成、**不擅自合并 PR / 删分支**。

## 拉取请求

**PR 不作为需求来源（PRs as a request surface: no）**。本仓库的 PR 只承载已完成并验收的工作。

## Wayfinding 操作（`/wayfinder` 用）

- **Map**：`docs/tickets/<effort>/README.md`（Notes / Decisions-so-far / Fog 三段）。
- **子票据**：`docs/tickets/<effort>/T<N>-<slug>.md`，`N` 从 1 起；`Type:` 行记类型（`research`/`prototype`/`grilling`/`task`），`Status:` 行记 `claimed`/`resolved`。
- **阻塞**：靠近顶部的 `Blocked by: T1, T3` 行。
- **Frontier**：扫 `docs/tickets/<effort>/` 里未完成、无阻塞、未被认领的票据，编号最小者优先。
- **认领**：先写 `Status: claimed` 再动手。
- **结题**：`## Answer` 段写答案，`Status: resolved`，再把上下文指针追加进 `README.md` 的 Decisions-so-far。
