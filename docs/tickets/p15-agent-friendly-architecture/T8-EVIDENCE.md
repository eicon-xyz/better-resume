# T8 证据：四个门禁进 `--layer scripts` 与派生产物 `--check` 聚合

## 意图复述

- 我理解这票解决什么：四个门禁脚本（凭据泄漏、历史叙事、引证存在性、票据结构）已经落地并各自带 `--selftest`，但没有一个被 `scripts/verify.sh` 的层体系调用——层里没有它们，CI 与本地就都看不见；票把门禁接进 `--layer scripts`，让「本地绿 = CI 绿」这条口径覆盖它们，并把派生产物的 `--check` 收敛成同一条可复跑命令。
- 我怎么做，到文件粒度：只改 `scripts/verify.sh` 的 `build_scripts()`——每个门禁按其两个入口各加一行 `add all`（`--selftest` 一行 + 全量扫描/结构校验一行）：secrets 跑 `--selftest` 与仓库扫描，docs_hygiene 跑 `--selftest` 与全树扫描，citations 跑 `--selftest` 与 `docs/tickets/**`（`find` 排除 `*-EVIDENCE.md`）扫描，ticket_frontier 跑 `--selftest` 与 `--check`（指向在飞阶段目录）；`render_list()` / `--dry-run` / 运行循环一律不动，新命令自动从同一份层计划渲染出来。
- 我不做什么：不改四个门禁脚本本身、不改任何生成物（`openapi.json` / `schema.d.ts` / skills 索引）、不引依赖、不重排既有层、不新增第二份命令清单、不把失败降级为警告；不动工作区里 p14 在飞的未提交改动；不 commit / push / 开 PR。

## 红-绿纪律（先红后绿）

### 红 1：门禁对已知坏输入必红（接线之前，未改 verify.sh）

```bash
cd "/root/better resume"
BAD=/tmp/t8-red-bad-tickets
mkdir -p "$BAD"
printf '# T1 坏票：缺 Status 行 + 悬空阻塞\nBlocked by: T9\n' > "$BAD/T1-bad.md"
printf '# T2 好票\nStatus: ready-for-agent\nBlocked by: 无\n' > "$BAD/T2-ok.md"
bash scripts/ticket_frontier.sh --check "$BAD"; echo "EXIT=$?"
printf '引证 no/such/file.py:3\n' > /tmp/t8-red-bad.md
bash scripts/verify_citations.sh /tmp/t8-red-bad.md; echo "EXIT=$?"
bash scripts/verify.sh --layer scripts --dry-run | grep -nE 'verify_secrets|verify_docs_hygiene|verify_citations|ticket_frontier' || echo '层计划里 0 处出现四个门禁（当前正是缺口）'
```

原始输出：

```text
--- 红 1：ticket_frontier --check 对已知坏票树 ---
EXIT=1
--- 红 2：verify_citations 对不存在的引证 ---
FAIL /tmp/t8-red-bad.md:1 引证「no/such/file.py:3」：文件不存在（整仓没有 basename 为 file.py 的文件）
引证 1（直配 0，短名兜底 0）解析成功 0 失败 1
EXIT=1
--- 红 3：接线的现状（层里有没有这四个门禁）---
层计划里 0 处出现四个门禁（当前正是缺口）

（红 1 的点名在 stderr：）
/tmp/t8-red-bad-tickets/T1-bad.md: 缺 Status 行
/tmp/t8-red-bad-tickets/T1-bad.md: Blocked by 指向不存在的票 T9
```

### 红 2：层把断言失败当失败（D22）

接线之前先把一条「拿已知坏票树当输入」的 frontier 命令临时放进 `build_scripts()` 首位，跑一次层：层在第 1 步就中止并退出非 0，证明运行循环不会把失败降级为警告。这条临时命令随后被正式接线替换，最终 diff 里没有它。

```bash
bash scripts/verify.sh --layer scripts; echo "EXIT=$?"
```

```text
[1/5] bash scripts/ticket_frontier.sh --check /tmp/t8-red-bad-tickets
/tmp/t8-red-bad-tickets/T1-bad.md: 缺 Status 行
/tmp/t8-red-bad-tickets/T1-bad.md: Blocked by 指向不存在的票 T9
EXIT=1
FAIL: bash scripts/ticket_frontier.sh --check /tmp/t8-red-bad-tickets (log: var/evidence/20261017T043743Z-scripts/01.log)
```

## 改了哪几节（文件粒度）

- `scripts/verify.sh` `build_scripts()`（第 96–110 行）：新增 8 行 `add all` + 3 段注释；`LAYER_ORDER`、`ALL_PARTS`、`add()`、`render_list()`、real 层、运行循环全部未动。
- 新增本证据文件 `docs/tickets/p15-agent-friendly-architecture/T8-EVIDENCE.md`。

```text
$ git diff --stat -- scripts/verify.sh
 scripts/verify.sh | 14 ++++++++++++++
 1 file changed, 14 insertions(+)

$ git status --porcelain -uall -- scripts/ docs/tickets/p15-agent-friendly-architecture/T8-EVIDENCE.md
 M scripts/verify.sh
?? docs/tickets/p15-agent-friendly-architecture/T8-EVIDENCE.md
```

## 验收命令原始输出

### 1. `--list` 含新命令，且渲染自层计划

```bash
export PATH="$HOME/.local/bin:$PATH"
cd "/root/better resume"
bash scripts/verify.sh --list
```

节选（scripts 层 + 派生产物所在的两层）：

```text
  api: cd apps/api && uv run python scripts/export_openapi.py --check
  api: cd apps/api && uv run python scripts/extract_api_index.py --check
  web: pnpm -C apps/web check:api
scripts:
  all: bash scripts/verify_secrets.sh --selftest
  all: bash scripts/verify_secrets.sh
  all: bash scripts/verify_docs_hygiene.sh --selftest
  all: bash scripts/verify_docs_hygiene.sh
  all: bash scripts/verify_citations.sh --selftest
  all: find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
  all: bash scripts/ticket_frontier.sh --selftest
  all: bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
all:
```

地图与展开同源，不是手抄：`--list` 的每一行都由 `render_list()` 调 `build_scripts()` 现渲染，`--layer scripts --dry-run` 是同一个 builder 的第二次调用，两者逐字相等（`tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs` 对每层做列表相等断言）。

### 2. `--layer scripts --dry-run` 的展开

```text
DRY RUN -- layer=scripts scope=all
  $ bash scripts/verify_secrets.sh --selftest
  $ bash scripts/verify_secrets.sh
  $ bash scripts/verify_docs_hygiene.sh --selftest
  $ bash scripts/verify_docs_hygiene.sh
  $ bash scripts/verify_citations.sh --selftest
  $ find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
  $ bash scripts/ticket_frontier.sh --selftest
  $ bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
  $ cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
  $ for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo 'shell syntax ok'
  $ uv run --project apps/api python scripts/check_scripts.py
  $ uv run --project apps/api python scripts/verify_audit_evidence.py --structural
```

### 3. `--layer scripts` 终态复跑：接线的前 8 步全绿，第 9 步红（红因不在本票）

```bash
bash scripts/verify.sh --layer scripts; echo "EXIT=$?"
```

原始输出（截去 pytest 的 traceback 中段，其余逐字）：

```text
[1/12] bash scripts/verify_secrets.sh --selftest
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
bad=detected (8/8 hits)
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 608 files)
selftest=PASS
[2/12] bash scripts/verify_secrets.sh
repo=clean (0 hits in 608 files)
[3/12] bash scripts/verify_docs_hygiene.sh --selftest
自检通过：11/11 个用例符合预期
[4/12] bash scripts/verify_docs_hygiene.sh
扫描 501 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
[5/12] bash scripts/verify_citations.sh --selftest
自检通过 6/6：好样本绿；不存在路径 / 行号越界 / 同名多文件三种坏样本都被判失败；围栏内放过、围栏外同款抓住
[6/12] find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
引证 104（直配 69，短名兜底 35）解析成功 104 失败 0
[7/12] bash scripts/ticket_frontier.sh --selftest
selftest: 8 项断言，失败 0 项
[8/12] bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
OK docs/tickets/p15-agent-friendly-architecture：结构校验通过（14 张票）
[9/12] cd apps/api && uv run pytest tests/test_fault_probe.py ... tests/test_verify_script.py ...
1 failed, 100 passed, 2 warnings in 8.17s
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
FAIL: cd apps/api && uv run pytest ... (log: var/evidence/20261017T043806Z-scripts/09.log)
EXIT=1
```

### 4. 未被第 9 步挡住的三步单独复跑

```text
$ for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
shell syntax ok
$ uv run --project apps/api python scripts/check_scripts.py
script syntax ok (24 python scripts, SyntaxWarning treated as an error)
STEP11_EXIT=0
$ uv run --project apps/api python scripts/verify_audit_evidence.py --structural
STRUCT llm_gateway/LG-09: apps/api/src/better_resume/llm_gateway/resolver.py:236-241 outside 1..235
STRUCT llm_gateway/LG-12: apps/api/src/better_resume/llm_gateway/resolver.py:236-241 outside 1..235
2 structural problem(s) in 10 unit(s)
STEP12_EXIT=1
```

### 5. 第 9 / 12 步的红归谁：在飞的 llm_gateway 重构，不是本票接线

- 工作区有并行智能体正在改 `apps/api/src/better_resume/llm_gateway/*`：`resolver.py` 的 mtime 是 2026-10-17 12:38:48、`xingyun_factory.py` 12:38:57，而这一次层运行是 12:38:06（日志目录 `20261017T043806Z-scripts`）。
- `resolver.py` 从 HEAD 的 244 行缩到工作区的 235 行，`docs/audit/units/llm_gateway.json` 里 `236-241` 两处引证因此越界。
- 对照实验（同一份 checker、同一份 units，只换树）：`git clone --shared` 出的 HEAD 检出上 strict 退 0，工作区退 1。

```bash
git clone --shared --quiet "/root/better resume" /tmp/t8-head
cd /tmp/t8-head && "/root/better resume/apps/api/.venv/bin/python" scripts/verify_audit_evidence.py --strict; echo "HEAD_STRICT_EXIT=$?"
cd "/root/better resume" && "/root/better resume/apps/api/.venv/bin/python" scripts/verify_audit_evidence.py --strict; echo "WORKTREE_STRICT_EXIT=$?"
```

```text
verifiable: 122  partial: 0  unverifiable: 0
HEAD_STRICT_EXIT=0
FAIL  [llm_gateway] LG-06 / PART [llm_gateway] LG-09 / LG-10 / LG-12 / PART [web] web-07 ...
verifiable: 121  partial: 1  unverifiable: 0
STRUCT llm_gateway/LG-09: apps/api/src/better_resume/llm_gateway/resolver.py:236-241 outside 1..235
STRUCT llm_gateway/LG-12: apps/api/src/better_resume/llm_gateway/resolver.py:236-241 outside 1..235
2 structural problem(s) in 10 unit(s)
WORKTREE_STRICT_EXIT=1
```

本票没动 `docs/audit/units/**`、没动 `llm_gateway/**`、也没动 `scripts/verify.sh` 里既有的那两行 audit 命令（`git diff` 只有 `build_scripts()` 顶部的 14 行新增）。

复跑窗口 12:40:50–12:45:31（10 次探测、每次隔 30 秒）里 `--structural` 与 `--strict` 始终非 0，且漂移集合在移动：后半段变成 `http/http-13`（`apps/api/src/better_resume/http/interview.py:491-493` 越界，该文件只剩 490 行）加 `interview_engine` 多条，说明工作区仍在被并行改动。等这些改动落定、`docs/audit/units/*.json` 重锚之后，`--layer scripts` 才有「退出 0」的读数可给；本票的接线部分不依赖它们。

### 6. 派生产物 `--check` 聚合（建议 8）

三个派生产物的判定都在层计划里，本地与 CI 走同一条命令（未新增依赖、未新增第二处判定）：

| 派生产物 | 层内命令 | 本次复跑读数 |
| --- | --- | --- |
| openapi.json ↔ schema.d.ts | contract(api) `uv run python scripts/export_openapi.py --check` + contract(web) `pnpm -C apps/web check:api` | `openapi.json is up to date` exit 0；`pnpm gen:api && git diff --exit-code -- src/api/schema.d.ts` exit 0 |
| skills/api 索引 | contract(api) `uv run python scripts/extract_api_index.py --check` | `API index is up to date` exit 0 |
| 层地图 | scripts 层 pytest 里的 `tests/test_verify_script.py`（`test_the_list_map_names_the_commands_each_layer_really_runs` 对每层做「地图 == 展开」列表相等断言） | 该文件本轮 `1 failed, 100 passed`，唯一失败是 audit 引证那条，地图相关断言全过 |

```text
$ cd apps/api && uv run python scripts/export_openapi.py --check
openapi.json is up to date
RC=0
$ cd apps/api && uv run python scripts/extract_api_index.py --check
API index is up to date
RC=0
$ pnpm -C apps/web check:api
$ pnpm gen:api && git diff --exit-code -- src/api/schema.d.ts
$ openapi-typescript ../api/openapi.json -o src/api/schema.d.ts
✨ openapi-typescript 7.13.0
RC=0
```

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 每个门禁接两行：`--selftest` 一行、全量扫描/结构校验一行 | 票面把「selftest 读数」与「全量扫描」并列成两件事；两行让 `--list` 上各自可见、各自有退出码，红的时候一眼看出是「门禁坏了」还是「树脏了」 | 没把两者合成一行脚本或写一个包装脚本——那会多一个文件、多一层转发 |
| `ticket_frontier.sh --check` 只指向在飞阶段目录 `docs/tickets/p15-agent-friendly-architecture` | `docs/tickets/*/` 全量循环会让层红：p11–p14 的票头部没有 `Status` 行（早期格式），而 `--check` 的头 20 行窗口就是判这个 | 没去补 p11–p14 的票面头部（他人在飞阶段，写入路径也不在我）；没写第二个阶段发现逻辑（如从 README 解析在飞阶段） |
| 引证的全量扫描用 `find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0` | 票面点名 `docs/tickets/**` 且排除证据文件；`-print0` 让含空格的路径不被拆开，空清单时 `xargs` 仍会调用一次并因缺参退出 2——偏向响亮失败而不是静默绿灯 | 没把扫描范围扩到 `docs/**`（全仓 markdown 的历史文档引证不是本票范围）；没给 `xargs` 加 `-r` |
| 门禁一律挂 `all` 标签、追加在 `build_scripts()` 既有四行之后 | 既有的 `bash -n` / `check_scripts.py` / audit 三行都用 `all`；追加而不是插队，避免动到 `test_scripts_layer_checks_the_scripts_themselves` 依赖的顺序语义 | 没改 `LAYER_ORDER` / `ALL_PARTS` / `--list` 说明行；没给 scripts 层加 `--scope` 守卫 |
| 派生产物的三个 `--check` 不新增命令，只核对它们已在层里 | contract(api)/contract(web) 已有这三条判定，scripts 层的 pytest 已钉住层地图；再加一条就是同一断言跑两遍 | 没在 scripts 层再抄一遍 openapi/api-index/schema 的 check（红线也禁止第二份） |

## 未验证项

- `bash scripts/verify.sh --layer scripts` 没有在本票拿到退出 0：第 9 步（层里既有那行 pytest 里的 audit `--strict` 测试）与第 12 步（层里既有的 audit `--structural`）红，红因是并行在飞的 `llm_gateway` 重构让 `docs/audit/units/llm_gateway.json` 的引证漂移（对照：HEAD 检出 strict 退 0）。等那份重构收工并重锚引证后需要复跑一次才能给出「退出 0」的原始读数；本次层运行里 [1/12]–[8/12] 与第 10、11 步全绿。
- `--layer contract` 整层没有跑（需要 DB 与前端依赖，且工作区有在飞的 p14 改动会引入与本票无关的红）；只逐条复跑了本票点名的三个派生产物命令。
- 没有在真实 `docs/tickets/**` 上注入坏引证来演示红（工作区写入路径只允许 `scripts/verify.sh` 与本证据文件）；红演示用的是 `mktemp`/`/tmp` 下的坏样本与临时坏票树。
- 没有验证 CI 侧的实际运行（不 push、不开 PR 是票面红线）；「本地与 CI 同一条命令」由 `.github/workflows/ci.yml` 调 `--layer scripts` 与本地调用同一个 script 保证，本次只做到逐字复跑该命令。
