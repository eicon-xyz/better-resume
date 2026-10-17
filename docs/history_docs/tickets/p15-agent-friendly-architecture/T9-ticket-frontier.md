# T9 票据结构校验与 frontier 输出（建议 1）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/ticket_frontier.sh`（新建，一个文件）

## 五栏

- 范围：读 `docs/agents/issue-tracker.md`（Status/Blocked by/Type 语义与 Frontier 规则）、`docs/tickets/p15-agent-friendly-architecture/` 各票样、`recall-report.md` F01/F19/F20。
- 唯一写入路径：`scripts/ticket_frontier.sh`（内置 `--check` 与 `--selftest`；只读票不写票）。
- 验收口径（原始输出贴进 T9-EVIDENCE.md）：
  1. `bash scripts/ticket_frontier.sh docs/tickets/p15-agent-friendly-architecture` 输出 frontier 一行：未完成、无阻塞、未认领中编号最小的票（`T<N> <文件名> <标题>`）；
  2. `--check` 模式：缺 Status 行、Blocked by 指向不存在的票、同号重名——任一出现退出非 0 并点名文件；合法树退出 0；
  3. `--selftest` 退出 0：内置一棵合法树与三类非法树，读数与预期一致。
- 红线：不改任何票据文件；不引入依赖（bash）。
- 不接受的自由度：frontier 判定严格按 docs/agents/issue-tracker.md，不许自创规则；脚本对票目录只读。

## Answer

scripts/ticket_frontier.sh 落地：frontier / --check / --selftest 三入口，8 项断言全过；接进 verify.sh 属 T8。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
