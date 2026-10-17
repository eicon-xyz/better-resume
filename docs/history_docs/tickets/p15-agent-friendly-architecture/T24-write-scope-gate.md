# T24 写入路径越界门禁（建议 12 的工具半边）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/`（红线内：新增 `verify_write_scope.sh` 与 `verify.sh` 的一行接线）

## 五栏

- 范围：读 `docs/agents/subagents.md` §8.2/§8.7（五栏与 sha256 基线口径）、`docs/tickets/p15-agent-friendly-architecture/` 各票头部「唯一写入路径」行、pitfalls-report P07。
- 唯一写入路径：`scripts/verify_write_scope.sh`（内置 --selftest）+ `scripts/verify.sh` 一行接线。
- 验收口径（原始输出贴进 T24-EVIDENCE.md）：
  1. `--selftest` 退出 0：内嵌好票（diff 全在声明内）绿、坏票（越界一个文件）红并点名文件与声明；
  2. 真票演示：对 p15 目录跑一次 `--check`（当前工作区真实 diff 对各票声明），读数贴证据；
  3. `bash scripts/verify.sh --layer scripts` 中该门禁 selftest 步骤绿（全层红若仅剩 IE-10 归 T22，写明归因）；
  4. 越界判定退出非 0（不许降级为警告）。
- 红线：不改票据文件；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：声明解析只认票头「唯一写入路径:」行的字面（文件或目录前缀），不许模糊猜测；sha256 基线比对不并入（那是派活流程动作，本工具只判 diff 越界）；远端闸门不做（硬规则 1 由人执行，工具化价值低于成本——此为有意简化，升级路径：pre-push hook）。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

scripts/verify_write_scope.sh 落地：票头声明字面 vs 真实 diff 的越界判定（9 用例自检、阶段并集/单票两模式、显式豁免），verify.sh 接线 +2 行。

### 追记（出票方验收）

- 复跑：自检 9/9；真票阶段读数 163 → 覆盖 103 / 越界 9 / 豁免 51（9 个越界 = 用户 p14 在飞自有改动，判定正确）；单票越界退非 0。
- 变异演示：范围判定行置 true → 坏票/前缀两用例漏判红，恢复逐字节一致（首砍锚点被 shell 引号吞，换引号免疫锚点后实红）。
- 层红归因认可（审计锚点 → T22）；远端闸门 / sha256 并入按票面有意简化，升级路径已记。
