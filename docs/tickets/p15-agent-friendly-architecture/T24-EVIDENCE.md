# T24 验收证据：写入路径越界门禁

## 意图复述

- 把「执行方只许写票头『唯一写入路径:』那一行声明的范围」从口头约定变成会红的判定：新增 `scripts/verify_write_scope.sh`，把改动清单与该行的字面 token 逐条比对，越界即非 0，并点名越界文件与它违反的那条声明。
- 本票只判 diff 越界这一件事：sha256 基线与远端闸门都不并入（票面「不接受的自由度」）；工具自己的判据由内置 `--selftest` 的好票/坏票样本证明，并在 `scripts/verify.sh --layer scripts` 里接一行。
- 写入路径只有 `scripts/`：新增该脚本 + `verify.sh` 一行接线；不改任何票据文件、不引依赖、不 commit/push/开 PR。

## 实现决定交代

| 决定 | 为什么 | 没做什么 / 代价 |
| --- | --- | --- |
| `--check <阶段目录>` 判「并集覆盖」：改动文件落在目录里任意一张票的声明内即合规；逐文件判定走单票模式 `--check <票文件>` | 工作区真实 diff 无法归属到某一轮某一票（工作区同时躺着 p14 在飞与全阶段各票的改动），阶段级唯一可判的问题是「每个改动文件是否被本阶段某张票声明」 | 并集看不出「本轮的票写了别人票的范围」——那条要用单票模式配 `--paths-from` 传本轮清单（升级路径：接 pre-push hook） |
| 声明解析 = 票头 HEAD_LINES(20) 行内那一行的全部反引号字面 token | 票面「只认票头那一行的字面，不许模糊猜测」；T21 把 `compose.yaml` 写在括号之后，按「第一个括号前截断」会漏掉真实声明 | 代价：T18/T15 括号里提到的 `verify.sh`、`compose_smoke.sh` 也进了声明（按仓库根路径匹配，永远匹配不到文件）——只放宽允许集，不掩盖越界 |
| 豁免按 `case` 明确点名三条：`*-EVIDENCE.md`、被检查目录里的 `T<N>-*.md` 与 `PROBLEMS.md` | §8.3 票据自身两段自述不算写入路径；票文件与台账是阶段规格与流程指定产物，不是某张票的写入产物 | 代价：被检查目录里的票文件改动本工具不判，那一半由 §8.7 的 sha256 基线负责；不做整目录豁免（否则会连 `docs/` 下真实越界一起放过） |
| 默认改动清单 = `git diff HEAD --name-only --no-renames -z` + `git ls-files --others --exclude-standard -z`；另给 `--paths-from` 传显式清单 | 票面要求「当前工作区真实 diff」；NUL 分隔避免引号/转义，重命名按「删 + 增」两条列出 | 代价：路径里含换行的仓库会在 NUL→换行归一化时错位；本仓库没有这种路径 |
| `verify.sh` 只接 `--selftest` 一行（另加一行注释） | 逐票真判定要「一票一 diff」；把工作区全量 diff 接进层必然整片红，只制造噪音。层里跑自检才有判别力 | 层不保证「当前工作区没有越界写入」——那是派活流程按本轮清单跑单票模式的动作 |
| 判不出来判 2：票头没有声明行 / 声明行里没有字面 token / 阶段目录里没有票文件 | D22：只打印结论不判定的脚本算缺陷；解析不出来却判 0 会让门禁永远绿 | 不猜短名、不补全路径、不给默认声明 |
| 判定与自证同源：`--selftest` 9 个内嵌用例（好票 / 坏票 / 目录前缀边界 / 同名后缀 / 豁免 / 空声明 / 阶段两态） | 门禁自己先被证明会红（`docs/agents/subagents.md` §4「核对脚本自己也要被验证」） | 用例是内嵌样本，不覆盖真实仓库的历史形态 |
| 读数行打出四个计数（改动 / 声明内 / 越界 / 豁免），越界明细点名文件与声明原文 | 判定透明：「0 命中」与「没跑」在输出里可区分 | 阶段模式逐票覆盖数是每票一行，26 张票的输出较长 |

## 验收读数

### 1. `--selftest`：内嵌好票/坏票样本（验收口径 1）

```text
$ bash scripts/verify_write_scope.sh --selftest
ok   好票（改动全在声明内）绿
ok   坏票（越界一个文件）红并点名文件与声明
ok   目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）
ok   文件声明精确匹配（AGENTS.md）
ok   文件声明不吃同名后缀（AGENTS.md.bak）
ok   豁免：票据自述 / 阶段票文件 / 台账不判
ok   票头没有声明行 → 判 2（不静默绿）
ok   阶段模式：并集覆盖全部改动 → 绿
ok   阶段模式：谁都不声明的文件 → 红并点名
selftest=PASS（9/9 个用例符合预期）
[exit 0]
```

红绿纪律的两条记录：

**红**：判定未接线（`in_scope` 恒真）时，同一条自检的读数是 4/9 不符预期——坏票、前缀边界、同名后缀、阶段越界四条全部漏判：

```text
FAIL 坏票（越界一个文件）红并点名文件与声明：期望退出码 1，实际 0
FAIL 目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）：期望退出码 1，实际 0
FAIL 文件声明不吃同名后缀（AGENTS.md.bak）：期望退出码 1，实际 0
FAIL 阶段模式：谁都不声明的文件 → 红并点名：期望退出码 1，实际 0
selftest=FAIL（4/9 个用例不符预期）
```

**绿**：接线后 9/9 通过（见上）。这个「红 → 绿」用当下文件可复跑的等价形式是变异证明（把判定改成恒真，自检必须红）：

```text
$ bash scripts/verify_mutation.sh --test "bash scripts/verify_write_scope.sh --selftest" --file scripts/verify_write_scope.sh --find '  [[ "$p" == "$e" || "$p" == "$e"/* ]]' --replace '  true'
== 1/3 baseline: the test must PASS on the untouched implementation ==
ok   好票（改动全在声明内）绿
ok   坏票（越界一个文件）红并点名文件与声明
ok   目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）
ok   文件声明精确匹配（AGENTS.md）
ok   文件声明不吃同名后缀（AGENTS.md.bak）
ok   豁免：票据自述 / 阶段票文件 / 台账不判
ok   票头没有声明行 → 判 2（不静默绿）
ok   阶段模式：并集覆盖全部改动 → 绿
ok   阶段模式：谁都不声明的文件 → 红并点名
selftest=PASS（9/9 个用例符合预期）

== 2/3 mutate: apply --find/--replace to scripts/verify_write_scope.sh ==
mutated 1 occurrence in scripts/verify_write_scope.sh

== 2/3 red: the test must FAIL on the mutated implementation ==
ok   好票（改动全在声明内）绿
FAIL 坏票（越界一个文件）红并点名文件与声明：期望退出码 1，实际 0
票：/tmp/tmp.U8bsvBfgxA/selftest/bad/T2-bad.md
声明行原文：唯一写入路径: `scripts/`
声明字面条目：scripts/
读数：改动 2 个文件 → 声明内 2，越界 0，豁免 0
OK：改动全部落在该票声明内

FAIL 目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）：期望退出码 1，实际 0
票：/tmp/tmp.U8bsvBfgxA/selftest/edge/T3-edge.md
声明行原文：唯一写入路径: `scripts/` 与 `AGENTS.md`
声明字面条目：scripts/ AGENTS.md
读数：改动 1 个文件 → 声明内 1，越界 0，豁免 0
OK：改动全部落在该票声明内

ok   文件声明精确匹配（AGENTS.md）
FAIL 文件声明不吃同名后缀（AGENTS.md.bak）：期望退出码 1，实际 0
票：/tmp/tmp.U8bsvBfgxA/selftest/edge/T3-edge.md
声明行原文：唯一写入路径: `scripts/` 与 `AGENTS.md`
声明字面条目：scripts/ AGENTS.md
读数：改动 1 个文件 → 声明内 1，越界 0，豁免 0
OK：改动全部落在该票声明内

ok   豁免：票据自述 / 阶段票文件 / 台账不判
ok   票头没有声明行 → 判 2（不静默绿）
ok   阶段模式：并集覆盖全部改动 → 绿
FAIL 阶段模式：谁都不声明的文件 → 红并点名：期望退出码 1，实际 0
阶段目录：/tmp/tmp.U8bsvBfgxA/selftest/stage-bad（2 张票）
每张票覆盖的改动文件数：
  /tmp/tmp.U8bsvBfgxA/selftest/stage-bad/T6-a.md：2
  /tmp/tmp.U8bsvBfgxA/selftest/stage-bad/T7-b.md：2
读数：改动 2 个文件 → 被声明覆盖 2，越界 0，豁免 0
OK：改动全部落在 /tmp/tmp.U8bsvBfgxA/selftest/stage-bad 各票声明的并集内

selftest=FAIL（4/9 个用例不符预期）
ok: mutation was caught

== 3/3 restore: the test must PASS again ==
restored: scripts/verify_write_scope.sh sha256=4d28045ea2f31fbf…
ok   好票（改动全在声明内）绿
ok   坏票（越界一个文件）红并点名文件与声明
ok   目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）
ok   文件声明精确匹配（AGENTS.md）
ok   文件声明不吃同名后缀（AGENTS.md.bak）
ok   豁免：票据自述 / 阶段票文件 / 台账不判
ok   票头没有声明行 → 判 2（不静默绿）
ok   阶段模式：并集覆盖全部改动 → 绿
ok   阶段模式：谁都不声明的文件 → 红并点名
selftest=PASS（9/9 个用例符合预期）

PASS: baseline green -> mutation red -> restored green (scripts/verify_write_scope.sh)
note: scripts/verify_write_scope.sh matches HEAD (no working-tree changes)
```

### 2. 真票演示：p15 目录 vs 当前工作区真实 diff（验收口径 2）

```text
$ bash scripts/verify_write_scope.sh --check docs/tickets/p15-agent-friendly-architecture
阶段目录：docs/tickets/p15-agent-friendly-architecture（26 张票）
越界：docs/DECISIONS.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/HANDOFF.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/agents/domain.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/agents/issue-tracker.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/agents/subagents.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/design/refs/README.md（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/design/refs/sample-mock-interview-page.png（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/design/refs/sample-resumes-page.png（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
越界：docs/design/refs/sample-sidebar.png（不属于 docs/tickets/p15-agent-friendly-architecture 里任何一张票的声明）
每张票覆盖的改动文件数：
  docs/tickets/p15-agent-friendly-architecture/T1-read-transcripts.md：1
  docs/tickets/p15-agent-friendly-architecture/T10-citation-fence-exempt.md：1
  docs/tickets/p15-agent-friendly-architecture/T11-fix-stale-citations.md：2
  docs/tickets/p15-agent-friendly-architecture/T12-sync-config-status.md：46
  docs/tickets/p15-agent-friendly-architecture/T13-cache-invalidation.md：46
  docs/tickets/p15-agent-friendly-architecture/T14-adapter-contract.md：46
  docs/tickets/p15-agent-friendly-architecture/T15-deploy-defaults.md：12
  docs/tickets/p15-agent-friendly-architecture/T16-clock-wait-primitive.md：46
  docs/tickets/p15-agent-friendly-architecture/T17-audit-reanchor.md：4
  docs/tickets/p15-agent-friendly-architecture/T18-hermetic-gate.md：16
  docs/tickets/p15-agent-friendly-architecture/T19-restore-read-path-write.md：46
  docs/tickets/p15-agent-friendly-architecture/T2-mine-commits.md：1
  docs/tickets/p15-agent-friendly-architecture/T20-build-for-model-protocol.md：5
  docs/tickets/p15-agent-friendly-architecture/T21-compose-build-escape.md：12
  docs/tickets/p15-agent-friendly-architecture/T22-final-reanchor.md：4
  docs/tickets/p15-agent-friendly-architecture/T23-flow-missing-error-semantics.md：46
  docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md：12
  docs/tickets/p15-agent-friendly-architecture/T25-pr-state.md：1
  docs/tickets/p15-agent-friendly-architecture/T26-rule-pointers.md：2
  docs/tickets/p15-agent-friendly-architecture/T3-synthesize-plan.md：1
  docs/tickets/p15-agent-friendly-architecture/T4-web-eslint-strict.md：30
  docs/tickets/p15-agent-friendly-architecture/T5-secrets-gate.md：1
  docs/tickets/p15-agent-friendly-architecture/T6-docs-hygiene-gate.md：1
  docs/tickets/p15-agent-friendly-architecture/T7-citation-gate.md：1
  docs/tickets/p15-agent-friendly-architecture/T8-verify-wiring.md：1
  docs/tickets/p15-agent-friendly-architecture/T9-ticket-frontier.md：1
读数：改动 163 个文件 → 被声明覆盖 103，越界 9，豁免 51
FAIL：9 个改动文件不属于 docs/tickets/p15-agent-friendly-architecture 任何一张票的声明
[exit 1]
```

读数口径：163 = 全部改动文件（`git diff HEAD` + 未跟踪，NUL 分隔去重）；51 = 豁免（阶段目录里的票文件、证据文件、PROBLEMS 台账）；103 = 落在某张票声明内；9 = 不属于本阶段任何一张票声明的改动（3 个阶段收口文档 + `docs/agents/` 三件 + `docs/design/refs/` 四件，属阶段外的在飞改动与设计参考图）。退出码 1。

### 2b. 单票模式：本票本轮的改动清单（逐文件判定）

```text
$ printf '%s\n' scripts/verify_write_scope.sh scripts/verify.sh docs/tickets/p15-agent-friendly-architecture/T24-EVIDENCE.md > /tmp/t24-round.txt
$ bash scripts/verify_write_scope.sh --check docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md --paths-from /tmp/t24-round.txt
票：docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md
声明行原文：唯一写入路径: `scripts/`（红线内：新增 `verify_write_scope.sh` 与 `verify.sh` 的一行接线）
声明字面条目：scripts/ verify_write_scope.sh verify.sh
读数：改动 3 个文件 → 声明内 2，越界 0，豁免 1
OK：改动全部落在该票声明内
[exit 0]

$ printf '%s\n' scripts/verify_write_scope.sh apps/web/src/App.tsx > /tmp/t24-round-bad.txt
$ bash scripts/verify_write_scope.sh --check docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md --paths-from /tmp/t24-round-bad.txt
票：docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md
声明行原文：唯一写入路径: `scripts/`（红线内：新增 `verify_write_scope.sh` 与 `verify.sh` 的一行接线）
声明字面条目：scripts/ verify_write_scope.sh verify.sh
越界：apps/web/src/App.tsx（不在这张票的声明内：scripts/ verify_write_scope.sh verify.sh）
读数：改动 2 个文件 → 声明内 1，越界 1，豁免 0
FAIL：docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md 越界 1 个文件
[exit 1]
```

### 3. `verify.sh` 接线与层读数（验收口径 3）

```text
$ bash scripts/verify.sh --layer scripts --dry-run
DRY RUN -- layer=scripts scope=all
  $ bash scripts/verify_secrets.sh --selftest
  $ bash scripts/verify_write_scope.sh --selftest
```

`bash scripts/verify.sh --layer scripts` 实际跑（带 `PATH`/`UV_CACHE_DIR`/`BR_DATABASE_URL`/`BR_REDIS_URL` 导出）：第 12 步（本门禁自检）绿：

```text
[12/16] bash scripts/verify_write_scope.sh --selftest
ok   好票（改动全在声明内）绿
ok   坏票（越界一个文件）红并点名文件与声明
ok   目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）
ok   文件声明精确匹配（AGENTS.md）
ok   文件声明不吃同名后缀（AGENTS.md.bak）
ok   豁免：票据自述 / 阶段票文件 / 台账不判
ok   票头没有声明行 → 判 2（不静默绿）
ok   阶段模式：并集覆盖全部改动 → 绿
ok   阶段模式：谁都不声明的文件 → 红并点名
selftest=PASS（9/9 个用例符合预期）
```

第 13 步红，全层退出 1：`tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`（审计引证逐字级）。读数 `verifiable: 118  partial: 2  unverifiable: 2`，与 T23-EVIDENCE.md 记录的读数逐字相同（这条红与本票无关）；4 条非逐字可证都是重锚欠账——`PART [identity_jobs] identity_jobs-03`、`PART [interview_engine] IE-10`、`FAIL [settings_observability] so-04` 等引 `main.py` 的锚点，归 T22（唯一写入路径 `docs/audit/units/`）；本票红线不许动 `docs/audit/`：

```text
=========================== short test summary info ============================
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
1 failed, 100 passed, 2 warnings in 7.38s
FAIL: cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py (log: var/evidence/20261017T064326Z-scripts/13.log)
EXIT=1
```

层在第 13 步中止，后三步未跑到，单独跑（命令原文取自 `scripts/verify.sh` 的 build_scripts）：

```text
$ for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
$ uv run --project apps/api python scripts/check_scripts.py; echo "[exit $?]"
$ uv run --project apps/api python scripts/verify_audit_evidence.py --structural; echo "[exit $?]"
shell syntax ok
script syntax ok (25 python scripts, SyntaxWarning treated as an error)
[exit 0]
structure ok: 10 units / 122 issues / 340 citations
[exit 0]
```

### 4. 越界判定退出非 0（验收口径 4）

三处原始读数：`--selftest` 里坏票/前缀/后缀/阶段越界四个用例全部退出 1（不降级为警告）；阶段模式真票演示 `[exit 1]`；单票模式的越界清单 `[exit 1]` 并点名 `apps/web/src/App.tsx`。

## 写入路径

- `scripts/verify_write_scope.sh`（新建）
- `scripts/verify.sh`（+2 行：1 行注释 + 1 行接线）
- `docs/tickets/p15-agent-friendly-architecture/T24-EVIDENCE.md`（票据自身两段自述，§8.3 不计入写入路径）

## 未验证项

- 只跑了 `--layer scripts`；unit / contract / coverage / deploy / e2e / fault / soak / real 各层未跑（本票只动 `scripts/` 与证据文件）。
- 没在 GitHub Actions 上跑过，读数全部来自本机工作区。
- 远端闸门与 pre-push hook 没做（票面有意简化，硬规则 1 由人执行）。
- sha256 基线比对没做（票面有意排除，属 §8.7 派活流程动作）。
- `--paths-from` 的清单由调用方产出，工具不产出；本轮演示里的清单是手工写的 `/tmp/t24-round.txt`。
- 阶段模式的并集判定看不出跨票越界（要靠单票模式 + 本轮清单），这条没有自动化用例覆盖。
- 路径里含换行的仓库未验证（清单在 NUL→换行归一化时会错位）。
- IE-10 那条引证红留给 T22，未在本票修（红线外）。
