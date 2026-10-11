# P9 验收包：`--list` 层地图与真实展开同源（＋ 两轴机械修复）

> 状态：**待用户验收**（AI 不自行宣布完成、未推送、未合并、未删分支）
> 分支：`fix/verify-map-truth`，从 `main` = `fd79375` 切出（PR #23 已合并的那个点）
> 提案：`docs/tickets/p9-verify-map-truth/README.md`（§8 的三项拍板：**A2 / B1 / C1**）
> 台账：`docs/tickets/p1-post-v/PROBLEMS.md` 的 **P44**

## 0. 一句话

`--list` 的层地图不再是第二份手写副本：它由**计划段**（每层自己的 builder）渲染，
并用一条**相等断言**钉住「地图 == 真实展开」。评审给的 12 条里，机械项全部闭环（每条红-绿各一次），
地图改造按你选的 A2 落地、`coverage` 按 B1 尊重 `--scope`；另有 4 条变异证明与一份**CI 侧逐字等价**对照。

## 1. 逐条证据（红 → 绿）

| # | 条目 | 缝（测试） | 修前（原始输出要点） | 修后 |
| --- | --- | --- | --- | --- |
| S3/P2/P5 | 地图是手写副本，与展开漂移 | `test_the_list_map_names_the_commands_each_layer_really_runs`（8 个参数化，逐字比较） | **25 tests / 7 failed**；unit・coverage・soak・real・scripts 五例各自报出「广告了没跑的命令 / 藏了真跑的命令」 | **26 / 0**（三条文件合计 **67 / 0**；加固后的读数） |
| S2 | 底线判定与写数据的 pytest 隐式顺序耦合 | `test_the_coverage_floor_runs_after_the_pytest_that_writes_its_data` | 变异证明第 2 步红（把 `add_coverage` 提前 → 测试红） | 绿 + 变异证明通过 |
| P6/S3 | `--layer coverage` 不读 `--scope` | `test_coverage_layer_respects_the_scope_flag` / `test_a_scope_with_nothing_to_run_says_so` | `--scope web` 照样跑整套 API pytest（实测 2 条命令） | `nothing to run for layer=coverage scope=web`（exit 0）+ scope 等价断言 |
| P1 | `test_list_exposes_every_layer` 元组缺 `coverage` | 同一条测试改为读**层头**并补全九层 | 元组 = 8 层（无 coverage），且断言只是子串包含 | 元组 = 9 层，断言读 `--list` 的层头；变异 M4 让它红 |
| S1【硬违规】 | `docs/HANDOFF.md:167` 仍写「钉 all ⊇ unit∪contract∪scripts」 | `docs/HANDOFF.md` 该行 | 原文含过期展开式（三层的 union） | 改为指针：「钉 `all` 的展开 ⊇ 各层展开，并钉 `--list` 的地图 == 真实展开」，不再复述层名 |
| S4 | 「16 条命令」是易腐缓存 | `AGENTS.md:61` / `docs/HANDOFF.md:74` | 两处都写死数字（本轮已实测变 16，正是它易腐的证据） | 改为「条数看 `--dry-run`/`--list`，别抄进文档」 |
| S5/P3 | P31 式发现没有台账号 | `docs/tickets/p1-post-v/PROBLEMS.md` | 无该行 | 新增 **P44**（现象 / 根因 / 修法 / 红绿证据四栏，含 `e0d4fa4` 那次改动） |
| P4 | PR #23 超出规格字面授权 | 本文件 §5 | — | 记为偏差（不回滚，理由见 §5） |

### 1.0 修前红 / 修后绿的**原始输出**（红绿证据本体）

复现手法：**只把 `scripts/verify.sh` 回退到 `main`、保留本分支的新测试**（这样量的是「一条真断言打在旧实现上」，
而不是「拿旧测试当基线」），跑完再把新脚本放回并核对逐字一致。产物：`var/p9-evidence/{red,green}.txt`（`var/` 已 gitignore，故原文收录于此）。

```
$ git show main:scripts/verify.sh > scripts/verify.sh   # 只换脚本，测试保持新
$ cd apps/api && ./.venv/bin/python -m pytest tests/test_verify_script.py -q -p no:randomly | tail
=========================== short test summary info ============================
FAILED tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs[unit]
FAILED tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs[coverage]
FAILED tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs[soak]
FAILED tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs[real]
FAILED tests/test_verify_script.py::test_the_list_map_names_the_commands_each_layer_really_runs[scripts]
FAILED tests/test_verify_script.py::test_coverage_layer_respects_the_scope_flag
FAILED tests/test_verify_script.py::test_a_scope_with_nothing_to_run_says_so
# 7 failed（当时：25 tests / 7 failed）

$ cp var/p9-evidence/verify_new.sh scripts/verify.sh && diff -q scripts/verify.sh var/p9-evidence/verify_new.sh
$ cd apps/api && ./.venv/bin/python -m pytest tests/test_verify_script.py -q -p no:randomly | tail
26 passed        # 修后绿（加固后读数；加固前为 25 passed）
```

一条代表性断言的原文（红时它就是这么喊的）：

```
E  AssertionError: --list advertises commands that layer unit does not run:
E    ['cd apps/api && uv run pytest']
E  and hides ones it does: ['cd apps/api && uv run pytest --cov=better_resume
E    --cov-report=json:coverage-api.json --cov-report=term']
```

### 1.1 四条变异证明（基线绿 → 变异红 → 恢复绿，脚本看退出码）

```
M1 改地图渲染（把 --cov-report=term 从 --list 输出里剥掉）
   -> 红：test_the_list_map_names_...[unit] / [coverage]        PASS（mutation was caught）
M2 把 add_coverage 挪到 add_api_unit 之前
   -> 红：test_the_coverage_floor_runs_after_the_pytest_that_writes_its_data   PASS
M3 让 build_coverage 的 scope 守卫永不触发
   -> 红：test_coverage_layer_respects_the_scope_flag / test_a_scope_with_nothing_to_run_says_so   PASS
M4 从 LAYER_ORDER 里删掉 coverage（地图少一层）
   -> 红：test_list_exposes_every_layer / ...[coverage]          PASS
四条在收口提交后**复跑一次**（加固重构之后）：各自 "restored: scripts/verify.sh sha256=6d89827e423038b8…"
（脚本自己核对恢复后的 sha256；重构前首轮读数是 59f28cdbbaf09e84…）
```

### 1.2 CI 侧逐字等价（本次唯一的行为变更就是 B1 那条）

把 `main` 的 verify.sh 与新版放进同一目录逐条对照 `--dry-run`（避免 ROOT 推导差异污染测量）：

```
SAME  unit/api        1 commands        SAME  contract/api    6 commands
SAME  unit/web        1 commands        SAME  contract/web    3 commands
SAME  scripts/all     4 commands        SAME  coverage/api    2 commands
SAME  all/api|web|all 16 commands       SAME  deploy/all      2 commands
SOAK EXPANSION IDENTICAL                REAL EXPANSION IDENTICAL
--- 拒绝语义不变 ---
--layer bogus / --layer unit --scope bogus / --layer coverage --scope bogus   旧=2 新=2
--list --scope bogus                                                        旧=0 新=0
--- 唯一有意变更 ---
--layer coverage --scope web:  旧 = 2 条命令  ->  新 = nothing to run（exit 0）
```

## 2. 每条改了什么（一句话）

1. **地图同源**：删掉 `MAP` heredoc；命令只在各层 builder 里声明一次，`add <tag> <cmd>` 同时记下 `--list` 该打印的标签；`--list` 遍历 `LAYER_ORDER` 逐层渲染。`real_steps` 提升为顶层数据（预检仍在执行路径上，`--list` 不碰凭据/音频/网络）。
2. **相等断言**：新测试只认 `api:`/`web:`/`all:` 行（散文留给真散文），对每层断言集合相等——包含式断言看不见「多打了半句注解」，相等才看得见。
3. **顺序断言**：`all` 的展开里，写 `coverage-api.json` 的 pytest 必须排在判底线的命令之前。
4. **scope 守卫**：`build_coverage` 在 `--scope web` 时直接返回空计划 → 走既有的 `nothing to run` 出口（不新增输出形状）。
5. **文档**：HANDOFF 167 行改指针；AGENTS/HANDOFF 的计数删除；PROBLEMS 补 P44。

## 3. 全量收口

**结果：ALL PASS（16 条命令）**，evidence = `var/evidence/20261009T023332Z-all`（收口后，含两轴评审驱动的重构与加固）。

```bash
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer all        # ALL PASS (16 commands) -- evidence: var/evidence/20261009T023332Z-all
python3 scripts/verify_audit_evidence.py --strict
```

### 3.1 数字（本次实测，全部出自同一条 `--layer all`）

| 项 | 读数 |
| --- | --- |
| `--layer all` | **ALL PASS（16 条命令）**，evidence = `var/evidence/20261009T023332Z-all` |
| 后端 pytest（带 `BR_*`） | **893 passed / 0 failed / 0 skipped**（78.23s） |
| 覆盖率底线 | `floors ok`（例：`resume_parser 93.2%` / `settings 98.6%` / `worker.py 84.2%`） |
| 前端 vitest | **177 passed（24 文件）** |
| ruff check / format --check | 干净（252 文件已格式化） |
| alembic upgrade / check、契约三件套 | 干净 |
| 审计引证 `--strict` | `verifiable: 122  partial: 0  unverifiable: 0` |
| 审计结构级（CI 层） | `structure ok: 10 units / 122 issues / 341 citations` |

## 4. 未验证项（诚实清单）

1. **`--layer real` 未真跑**（零真机调用）：只做了 `--dry-run` 与「旧/新展开逐字相同」的对照；预检路径（凭据/音频/`curl /healthz`）本轮**只靠既有测试**（`tests/test_real_layer.py` 6 例全绿）覆盖，没有真跑一次完整 real 层。
2. ~~**CI 未跑**~~ → **已出（PR #24，2026-10-09）**：backend **pass 3m42s** / frontend **pass 51s**，`mergeState=CLEAN`（run 37875536597）。
3. **`--list` 的输出形状变了**：`coverage:` 段第一行由散文占位变成真命令；`real:` 段由 1 行散文变成 5 条命令 + 2 行注解；`scripts:` 段两行注解移到段尾。仓库内无其它消费者（grep 过 `--list` 只命中测试与本文档），但**外部读者的肌肉记忆**无法自动验证。
4. **`--list` 忽略 `--scope`**（有意）：`--list --scope web` 仍打印完整计划。这是为「地图不能因 scope 而缺层」；已在脚本头注释与本文件写明，但**没有测试**钉它。
5. **P1 的「补元组不会红」是推理**（元组只多了一个已存在的层名）：其红由变异 M4 提供，不是天然红。
6. **未重锚任何审计引证**（本轮没碰被 `docs/audit/units/*.json` 引用的代码文件；`--strict` 实测仍 0 partial 可证）。
7. **`docs/architecture/` 与 `scripts/build_architecture_map.py` 未跟踪、未动**（他人的产物，按交接文档要求绕开；也未 `git add -A`）。

## 5. 与提案的偏差

1. **P4（PR #23 超规格授权）**：规格只授权把元组扩成四层，实际还含 scripts 段 3 行 MAP 改名 + 2 条新测试，**且已合并**（`fd79375`）。回滚属行为回退且无收益，故按闸门 3 记为偏差、不回滚。
2. **交接文档的 PR 状态过期**：交接写「PR #23 OPEN」，实测 `2026-10-09T02:03:48Z` 已合并（CI 双 job success）。故本轮不从 `fix/verify-all-covers-coverage` 续做，改从 `main` = `fd79375` 切新分支——与交接 §0 的字面指示不一致，理由如上。
3. **`--list` 的注解位置有变动（提案未预见）**：原 MAP 把「byte-level checking stays the manual --strict close-out step」写在第 3、4 行之间，渲染后统一挪到该段末尾（注释行不属于命令，相等断言不受影响；`test_the_list_map_does_not_advertise_the_manual_strict_gate` 仍绿）。
4. **提案 §3.4 说「补元组不会红」**：实测确实不红（见 §4.5），与提案一致，此处只作重申。
5. **P44 记在了既有台账里，没有新建 `docs/tickets/p9-verify-map-truth/PROBLEMS.md`**（提案 §5 的交付物表写的是一个新文件）。
   理由：P44 是 P31 的同族问题，**与 P31 同一张表**才有对比价值；分两个文件反而让读者看不到「第三次发生」这条主线。
   本目录因此只有 `README.md` 与 `ACCEPTANCE.md`（＋两轴评审的 `REVIEW.md`）。

## 6. 复跑命令（逐条）

```bash
# 1 地图/展开同源 + scope + 顺序（加固后 26 例）
cd apps/api && uv run pytest tests/test_verify_script.py -q -p no:randomly
# 2 real 层既有契约（6 例）与脚本契约
uv run pytest tests/test_real_layer.py tests/test_scripts_contracts.py -q -p no:randomly
# 3 四条变异证明（逐个跑，脚本自己核对恢复 sha256）
bash scripts/verify_mutation.sh --test "cd '/root/better resume/apps/api' && ./.venv/bin/python -m pytest tests/test_verify_script.py -q -p no:randomly" \
  --file scripts/verify.sh --find 'echo "  ${tags[$i]}: ${cmds[$i]}"' \
  --replace 'echo "  ${tags[$i]}: ${cmds[$i]//--cov-report=term/}"'
# 4 地图长什么样
bash scripts/verify.sh --list
bash scripts/verify.sh --layer coverage --scope web --dry-run     # nothing to run
```

> pytest 命令都要先导出 `BR_*`（不导出会静默 skip 136 条，而不是失败）。

## 7. 两轴 /code-review（阶段 4）

见 `docs/tickets/p9-verify-map-truth/REVIEW.md`（Standards 与 Spec 两轴并列、不合并、不重排）。


## 8. 两轴评审驱动的追加加固（阶段 4 之后）

两轴（`REVIEW.md`）回来后有 **5 条**值得当场闭环，已全部红-绿或等价验证：

| # | 发现（轴） | 修法 | 验证 |
| --- | --- | --- | --- |
| 1 | 相等断言是**集合**比较，顺序与重复不可见（Spec a-2） | 改为列表**逐字**比较 | `test_the_list_map_names...` 26 例绿 |
| 2 | 地图与展开对 `soak` 仍可能逐字不一致（变量未展开） | `evidence_dir` 在脚本顶部展开一次，命令串即最终文本 | `SOAK EXPANSION IDENTICAL`（与 `main` 逐字） |
| 3 | 5 个纯转发 builder（Standards 坏味道 1） | 删掉转发层，层构建器即真实定义 | 各层展开不变（等价脚本复跑 SAME） |
| 4 | `build_layer()` 的九路 case 与层名单重复（Standards 坏味道 2） | 改为按名字派生 `build_$LAYER` | 层×scope 展开与 `main` 逐字相同 |
| 5 | `--list` 忽略 `--scope` 属**未被规格授权**的行为（Spec b-1） | 保留该行为（地图不能因无关开关缺层），补测试把它由暗行为变成规范 | 新例绿 |

评审另外 3 条：① 提案缺「预估」段（已补 §8.5）；② 提案承诺的 `PROBLEMS.md` 未新建（改为真实落点 + §5.5 记偏差）；
③ 提案头「待你点头」与已实施矛盾（改为「已拍板并实施完毕」，并注明保留原文不改写）。

> 口径说明：本节的 26 / 67 是**加固后**的读数；§1 表里的 25 / 7 是加固**前**的红，两者不是同一次运行。
