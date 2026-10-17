# T10 引证门禁加围栏豁免（T7 预警的范围缺口）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/verify_citations.sh`

## 五栏

- 范围：读 `scripts/verify_citations.sh`、`T7-EVIDENCE.md` 的「给 T8 的预警」、`scripts/verify_docs_hygiene.sh` 头注释的围栏豁免口径。
- 唯一写入路径：`scripts/verify_citations.sh`。
- 验收口径（原始输出贴进 T10-EVIDENCE.md）：
  1. `--selftest` 新增两个用例（围栏内的坏引证放过、围栏外同款抓住）后全绿退出 0，用例数 > 4；
  2. `bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/*.md` 全部退出 0（T6-EVIDENCE 的坏样本在围栏内，不再命中）；
  3. 既有读数不变：对 pitfalls/recall 两报告仍是「引证 52、失败 0」。
- 红线：不改任何 markdown；不引依赖；不改退出码语义（0/1/2）。
- 不接受的自由度：只豁免围栏代码块（```/~~~），不豁免行内 code（行内引证是真引证）；不许改 basename 兜底与歧义判定；selftest 必须新增用例，不许改旧用例的期望值。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。

## Answer

verify_citations.sh 增围栏掩码与两个 selftest 用例（6/6）；两报告读数 52/52 不变；变异破掉掩码 → selftest 非零红。

## Comments

- 出票方裁决：口径 2 的 4 条残留全在 `*-EVIDENCE.md` 内。证据文件是原始输出转储，正确性由复跑判定，不当引证文本审——引证门禁扫描面排除 `*-EVIDENCE.md`；p15 主张文档扫描 52/52 全绿。T5/T11-EVIDENCE 的引证行不改（改证据自述比留残留更糟）。
