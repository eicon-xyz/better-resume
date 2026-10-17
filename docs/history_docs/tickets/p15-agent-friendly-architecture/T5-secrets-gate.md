# T5 凭据泄漏门禁 verify_secrets.sh（建议 15，含建议 7 的自检口径）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/verify_secrets.sh`（新建，一个文件）

## 五栏

- 范围：读 `docs/tickets/p15-agent-friendly-architecture/recall-report.md` F04、`pitfalls-report.md` P09、AGENTS.md 环境准备凭据条款、`.env.example`；脚本风格参考 `scripts/verify.sh`、`scripts/verify_mutation.sh`（set -euo pipefail）。
- 唯一写入路径：`scripts/verify_secrets.sh`（内置 `--selftest`，样本内嵌）。
- 验收口径（原始输出贴进 T5-EVIDENCE.md）：
  1. `bash scripts/verify_secrets.sh --selftest` 退出码 0，输出含 `bad=detected` 与 `repo=clean` 两行读数；
  2. `bash scripts/verify_secrets.sh` 扫仓库（排除 .git/ var/ node_modules/ docs/history_docs/ *.zstd）命中 0、退出码 0；
  3. 破坏演示：临时样本写入形如 sk- 前缀的假值后脚本退出非 0 并点名 文件:行号，同一命令内删除样本。
- 红线：不改任何现有文件；selftest 只用假样本，真实凭据不入脚本与输出；不引入依赖（纯 bash + grep/awk）。
- 不接受的自由度：不许只打印不判定（D22：以退出码判定）；不许模糊匹配误伤 `.env.example`（只写变量名）与打码文本 `<已打码>`；不许存在第二份扫描实现。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Answer

verify_secrets.sh 落地：6 形状判据、自检 8/8 坏样本全抓、仓库 0 命中；出票方变异演示删 sk- 模式 → bad=missed 7/8 红，恢复一致。

### 追记

- 票面 Status 收口迟滞属出票方记账遗漏（Spec 轴评审 S2 指出后补齐）；交付物与验收读数此前已核，无行为影响。
