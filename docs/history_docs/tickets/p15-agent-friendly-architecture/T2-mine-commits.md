# T2 解剖历史提交：智能体最常踩的坑

Type: research
Status: resolved
Blocked by: 无
唯一写入路径: `docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md`（新建）与 `docs/tickets/p15-agent-friendly-architecture/T2-EVIDENCE.md`（新建，仅两段自述）

## 范围

- `git log` 全部已提交历史（remote `eicon-xyz/better-resume`，至 HEAD `b09bbd2`）；工作区未提交改动不看。
- 方法先读：`/root/.dsh/skills/correct/SKILL.md`、`/root/.dsh/skills/architect/references/design-red-flags.md`。
- 判定参照：`CODING_STANDARDS.md`、`AGENTS.md`、`docs/DECISIONS.md`（什么算偏差）。
- 只读；读不到停下来报。

## 交付物与格式

`pitfalls-report.md`（简体中文）：

- `# pitfalls-report：智能体重复犯的错误类`
- `## 方法与覆盖`：总提交数、时间范围、用到的命令。
- `## 坑频次榜`：条目标题 `### P<NN> <坑名>`，按证据条数降序，每条四行：
  - `出处：<commit sha> <subject>；<文件:行号>`（可多条；≥2 条才算一类）
  - `原文摘录：<diff 或文件片段>`
  - `频次：<N>（计数命令：<可复跑命令>）`
  - `哪一层能消灭它：代码架构 / 类型 / lint·CI / 测试 / 文档`（correct 修复阶梯取最高层）
- `## 单次个案`：只出现一次、不构成类的。
- `## 对 agent-friendly 重架构的含义`：只写什么样的结构能让这类坑写不出来，不写具体方案。
- `## 未覆盖`：诚实清单。

## 验收口径

- `grep -c '^### P' pitfalls-report.md` ≥ 10。
- `grep -c '^出处：' pitfalls-report.md` 等于 `grep -c '^### P' pitfalls-report.md`。
- `grep -c '^频次：' pitfalls-report.md` 等于 `grep -c '^### P' pitfalls-report.md`。
- 交付前自己跑这三条，原始输出贴进 T2-EVIDENCE.md。

## 红线

- 不写唯一写入路径之外的任何文件；不动代码、不动工作区未提交改动、不动其他票据。
- 禁止 `git checkout` / `reset` / `clean` / `stash` 等改状态命令。
- 凭据不入报告。

## 不接受的自由度

- 每条必须有 sha + 文件:行号 + 摘录，缺一删条；不许凭印象写。
- 「频次」必须由可复跑命令得出，不许手数。
- 决策不算坑（「我们决定 X」不是错误类）；坑 = 同类错误被重复犯。
- 不许给具体重构方案（T3 的事）。
- 不许改写仓库既有文档。

## 意图复述与实现决定交代

同 T1：两段自述追加进 T2-EVIDENCE.md，「实现决定交代」没内容写「无」，不许留空。

## Answer

重复错误类 [P01]–[P12] 已排出坑频次榜进 pitfalls-report.md；三条验收读数 12/12/12，12 条频次命令逐条复跑一致。
