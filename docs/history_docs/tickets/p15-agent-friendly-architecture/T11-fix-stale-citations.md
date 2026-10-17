# T11 修掉 p11/p12 的失效引证（P09 的真实实例）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `docs/tickets/p11-resume-driven-questions/` 与 `docs/tickets/p12-intent-alignment/`（仅限门禁点名的引证行）

## 五栏

- 范围：跑 `bash scripts/verify_citations.sh docs/tickets/p11-resume-driven-questions/*.md docs/tickets/p12-intent-alignment/*.md` 取失败清单（基线读数：全树 364 条引证、失败 6，其中 p11 README 的 `orm.py` 三条歧义、p12 ACCEPTANCE 的 `settings_config.py` 不存在；p15 的两条属 T10）。
- 唯一写入路径：上述两目录内被门禁点名的文件的引证行。
- 验收口径（原始输出贴进 T11-EVIDENCE.md）：
  1. 上述命令退出 0、失败 0；
  2. `git diff --numstat` 只含这两个目录，且改动行数 ≤ 修复条数；
  3. 非引证文字零改动。
- 红线：不动 `docs/tickets/p15-agent-friendly-architecture/` 与其他文档；不改章节结构与编号；不 commit/push/开 PR。
- 不接受的自由度：歧义短名必须改成唯一全路径（不许删引证了事）；找不到对应文件的引证改为指向真实存在的位置，确实无对应才整句删并在「实现决定交代」记明；不许把改动追认成新规则（AGENTS.md 硬规则 3）。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Answer

4 条失效引证修毕（3 条 orm.py 短名歧义重锚全路径、1 条改指真实 settings 模块），两目录门禁 21/21 绿，diff 恰 4 行。

## Comments

- 出票方裁决：实现决定 A（重锚行号）与 B（改指真实 settings 模块）均采纳——门禁绿但引证撒谎正是 P09 要消灭的形态，A 的处理是对的；B 不引 gitignored 的 var/ 材料符合证据口径。
- 两处残留（p11 README §1.2 快照措辞、p12 ACCEPTANCE:69 措辞）保持原样：它们是提案成文时点的现状快照，按 docs/agents/issue-tracker.md「既有票据不回填」原则不追溯改写；语义漂移的复核留给阶段收口时一并做。
