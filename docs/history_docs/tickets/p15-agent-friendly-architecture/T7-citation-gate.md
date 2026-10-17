# T7 引证解析门禁 verify_citations.sh（建议 9）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/verify_citations.sh`（新建，一个文件）

## 五栏

- 范围：读 `recall-report.md` F15/F16、`pitfalls-report.md` P09、README 原型结论 C（52 条引证、44 直配 + 8 短名唯一命中）。
- 唯一写入路径：`scripts/verify_citations.sh`（内置 `--selftest`）。
- 验收口径（原始输出贴进 T7-EVIDENCE.md）：
  1. `bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md docs/tickets/p15-agent-friendly-architecture/recall-report.md` 引证 52、解析成功 52、失败 0、退出 0（短名按唯一 basename 解析）；
  2. `--selftest` 退出 0：内置坏样本（不存在的路径、行号越界、同名多文件的短名）必须全被判失败；
  3. 对 T1-EVIDENCE.md、T2-EVIDENCE.md 扫描退出 0。
- 红线：不改任何报告与证据文件；不引入依赖。
- 不接受的自由度：解析失败必须退出非 0（不许降级为警告）；短名多匹配必须判失败（不许任选一个）；验收不许手写条数当读数（以命令输出为准）。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Answer

verify_citations.sh 落地：路径/行号/短名兜底解析 + 自检 6/6（含 T10 围栏豁免两例）、两报告 52/52；出票方变异放宽歧义判定 → 歧义用例红。

### 追记

- 票面 Status 收口迟滞属出票方记账遗漏（Spec 轴评审 S2 指出后补齐）；交付物与验收读数此前已核，无行为影响。
