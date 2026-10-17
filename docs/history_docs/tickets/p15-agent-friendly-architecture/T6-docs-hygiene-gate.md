# T6 历史叙事门禁 verify_docs_hygiene.sh（建议 10）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/verify_docs_hygiene.sh`（新建，一个文件）

## 五栏

- 范围：读 `recall-report.md` F06、AGENTS.md 硬规则 2、CODING_STANDARDS.md §6 模板措辞、README 原型结论 B（含 84f622b 阳性样本）。
- 唯一写入路径：`scripts/verify_docs_hygiene.sh`（内置 `--selftest` 与显式豁免清单）。
- 验收口径（原始输出贴进 T6-EVIDENCE.md）：
  1. `bash scripts/verify_docs_hygiene.sh --selftest` 退出 0：内置阳性样本（历史叙事措辞）必须被抓住、阴性样本（含 CODING_STANDARDS 式不适用模板措辞、围栏代码块里的引证）必须放过；
  2. `bash scripts/verify_docs_hygiene.sh` 扫 docs/（除 docs/history_docs/）、skills/、AGENTS.md、GLOSSARY.md、CODING_STANDARDS.md 与源码注释，命中 0、退出 0；
  3. 禁词集在脚本顶部一个数组里，逐条注释为什么不误伤；AGENTS.md 硬规则 2 的 3 行引用用脚本内显式豁免清单（按原文精确匹配 + 逐条理由）处理。
- 红线：不改任何现有文档（豁免写在脚本内）；不引入依赖。
- 不接受的自由度：不许整文件/整目录模糊豁免（docs/history_docs/ 除外）；不许只打印不判定；围栏代码块与行内 code 的处理规则必须写明且被 selftest 覆盖。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Answer

verify_docs_hygiene.sh 落地：收窄禁词集 5 条 + 围栏/行内豁免 + 显式豁免清单，自检 11/11、532 文件 0 命中；出票方变异删 PATTERNS 条目 → 红。

### 追记

- 票面 Status 收口迟滞属出票方记账遗漏（Spec 轴评审 S2 指出后补齐）；交付物与验收读数此前已核，无行为影响。
