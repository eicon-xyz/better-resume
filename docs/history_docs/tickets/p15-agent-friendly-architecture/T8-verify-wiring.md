# T8 verify.sh 接线：门禁进层与派生产物 --check 聚合（建议 7 + 8）

Type: task
Status: resolved
Blocked by: T5, T6, T7, T10, T11
唯一写入路径: `scripts/verify.sh`

## 五栏

- 范围：读 `scripts/verify.sh` 现有层计划与渲染机制、T5/T6/T7 的三个门禁脚本、README 建议 7/8。
- 唯一写入路径：`scripts/verify.sh`（不改三个门禁脚本本身）。
- 验收口径（原始输出贴进 T8-EVIDENCE.md）：
  1. `bash scripts/verify.sh --list` 输出含新命令，且渲染自层计划（不许出现手抄的第二份命令清单）；
  2. `bash scripts/verify.sh --layer scripts` 退出 0，输出含四个门禁（secrets / docs_hygiene / citations / ticket_frontier）selftest 的读数；并跑全量扫描：secrets 仓库扫描、docs_hygiene 全树、citations 对 `docs/tickets/**`（排除 `*-EVIDENCE.md`——证据文件是原始输出转储，正确性由复跑判定）——全部退出 0；`ticket_frontier.sh --check` 进层；
  3. 派生产物 --check 进层：openapi.json↔schema.d.ts、层地图、skills/api 索引各自的 check 命令被聚合（本地与 CI 同一条命令），对应层跑完退出 0；
  4. 断言失败时退出非 0（D22：只打印不判定视为缺陷）。
- 红线：不改门禁脚本内容、不改生成物本身、不引入依赖。
- 不接受的自由度：不许重排既有层的命名与顺序（CI 依赖）；不许手写第二份层地图；不许把失败降级为警告。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Comments

- 出票方裁决：T8 按「8 步接线全绿 + 既有 audit 两行的红归因于 T12 在飞重构」验收接线本身；`--layer scripts` 最终退出 0 的读数并入 T17（audit 引证重锚 + 层收口）的验收口径，由出票方串行复跑取证。
## Answer

四门禁（secrets/docs_hygiene/citations/ticket_frontier）各 selftest+全量扫描共 8 行接进 build_scripts()，verify.sh +14/-0；--list 与 --dry-run 同源渲染出 8 条；派生产物 --check 三处全绿，未新增第二份判定。层最终退出 0 并入 T17 口径。

## Comments

- 出票方验收：接线 8 步全绿 + diff 14/0 + 四门禁 selftest 复跑全绿；`--layer scripts` 的退出 0 读数待 T17（audit 引证重锚）后由出票方串行复跑取证（裁决已见前置 Comments）。
- 已知缺口（进评审清单）：「门禁被接线」这件事本身没有会红的断言——删掉 add 行后 --list 与 --dry-run 仍然相等；由 T17 验收或评审定夺是否补断言。
