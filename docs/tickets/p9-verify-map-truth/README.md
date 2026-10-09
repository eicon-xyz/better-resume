# P9 提案：`--list` 层地图由计划段生成（＋ /code-review 两轴发现的机械修复）

> 依据：`/code-review` 的两轴结论（基点 `main...HEAD`，随 PR #23 交付）＋本轮**重新实测**的漂移测量（§1；
> 评审当时只给了「MAP 是手写散文」这一判断，没有量化，本提案把它量出来了）。
> 状态：**待你点头**（闸门 1）。规格写完不进 implement，等你确认 A/B/C 三个拍板点（§8）。
> 前情修正：交接文档 `handoff-better-resume-20261009.md` §1 的「PR #23 OPEN」**已过期** ——
> PR #23 于 **2026-10-09T02:03:48Z 合并**（merge commit `fd79375`，CI 双 job success），
> 故本阶段从 `main` = `fd79375` 重新切分支（不追已经合并的历史分支）。

## 1. 现状盘点（实测，非评审口径）

### 1.1 地图与展开的漂移（本轮实测，2026-10-09）

只读探针：对每一层跑 `--dry-run`，把 `$ ` 命令行与 `--list` 里该层的命令行做集合比对（脚本自写，产物在 `var/`，不入库）。

| 层 | 地图行 | 真实命令 | 不一致 |
| --- | --- | --- | --- |
| unit | 2 | 2 | **1 条地图行错**（地图写裸 `pytest`，真实是带 `--cov` 的那条） |
| contract | 9 | 9 | 0 |
| coverage | 2 | 2 | **1 条**（地图是散文占位「the same pytest command as unit: api」，不是命令） |
| deploy | 2 | 2 | 0 |
| fault | 1 | 1 | 0 |
| soak | 1 | 1 | **1 条**（地图缺 `mkdir -p` 前缀与 `--base`，`--json` 是相对路径而真实是绝对＋加引号） |
| scripts | 4 | 4 | **2 条**（`bash -n` 少 `; echo shell syntax ok`；`check_scripts.py` 带的一句注解不是命令的一部分） |
| real | 1（散文） | 5 | **地图只有「(T4) budget-guarded …; refuses until implemented」一句，真实展开 5 条** |

**结论：21 条地图行里 5 条与真实展开对不上**（另有 real 层整层未进地图）。
这不是「措辞不够精确」——`test_the_list_map_does_not_advertise_the_manual_strict_gate` 已经是靠**字符串匹配地图行**来判定的，
地图只要再漂一次，那条测试就会开始保护一个不存在的东西（P31 同族：标签与展开各自漂移）。

### 1.2 两轴 12 条的落地判定（每条：真 / 部分真 / 已消解）

| # | 轴 | 发现 | 本轮判定 |
| --- | --- | --- | --- |
| S1 | Standards | `docs/HANDOFF.md:167` 仍写「钉 all ⊇ unit∪contract∪scripts」，测试已扩成四层 | ✅ **真（硬违规）**：实测该行原文确实只有三层 |
| S2 | Standards | `add_coverage` 靠 `coverage-api.json` 隐式顺序依赖（注释已自认），无顺序断言 | ✅ 真 |
| S3 | Standards | `--list` MAP 是手写散文（治标）；同处缺陷 `--layer coverage` 不读 `--scope` | ✅ 真（§1.1 已量化；scope 实测见 §1.3） |
| S4 | Standards | `AGENTS.md:61` / `docs/HANDOFF.md:74` 的「16 条命令」是易腐缓存 | ✅ 真（上一提交 `ca50da6` 刚删掉「863 例/175 例」，同一类） |
| S5 | Standards | `e0d4fa4` 的 P31 式发现没有台账号 | ✅ 真（P31 在 `p1-post-v/PROBLEMS.md`，`e0d4fa4` 无对应行） |
| P1 | Spec | `test_verify_script.py:29` 元组仍缺 `coverage` | ✅ 真（元组 = unit/contract/deploy/fault/soak/real/scripts/all） |
| P2 | Spec | MAP 的 `unit:` 行是不带 `--cov` 的简写；`bash -n` 与 `check_scripts.py` 两行仍能无声漂移 | ✅ 真（= §1.1 的 5 条） |
| P3 | Spec | 台账号缺失（同 S5） | ✅ 真（合并处理） |
| P4 | Spec | scripts 段 3 行 MAP ＋ 新增 2 条测试 ＋ 改名超出规格字面授权 | ✅ 真（**已随 PR #23 合并**，只能记为偏差，见 §7） |
| P5 | Spec | 新测试「集合包含」判定，`all` 与 `coverage` 共用 builder → 相同命令串处等于自证 | ✅ 真（`all` 的 `add_api_unit` 与 `coverage` 的逐字相同，包含判定对这几条无鉴别力） |
| P6 | Spec | `coverage` 不读 `--scope`，而新 MAP 把「忽略 scope」写成了规范 | ✅ 真（实测：`--layer coverage --scope web` 照样跑整套 API pytest，见 §1.3） |

### 1.3 两条实测（复跑命令与输出）

```
$ bash scripts/verify.sh --layer coverage --scope web --dry-run
DRY RUN -- layer=coverage scope=web
  $ cd apps/api && uv run pytest --cov=better_resume --cov-report=json:coverage-api.json --cov-report=term
  $ cd apps/api && uv run python scripts/check_coverage_floors.py --json coverage-api.json

$ bash scripts/verify.sh --layer all --dry-run | grep -c "^  \$ "
16                      # AGENTS.md:61 / HANDOFF.md:74 把这个数字写死了
```

> `real` 层的预检（凭据/音频/栈健康）都在**展开之前**，所以 `--dry-run` 必须在 `.env` 与 fixture 都在时才能过；
> 本轮实测两者都在（`.env` 在、`data/audio/p1c-multi-sentence-16k.wav` 在），dry-run 干净。

## 2. 目标（本轮范围）

1. **地图与展开同源**：`--list` 的输出由「计划段」直接渲染，不再有第二份手写副本；并用一条**相等断言**（不是包含）钉死。
2. **两轴的机械项全部闭环**：S1/S2/S4/S5（=P3）/P1/P4 逐条有红有绿。
3. **`--scope` 语义要么修、要么写明**（P6/S3 的同一处缺陷），不留「MAP 把忽略 scope 描述成有意为之」这种状态。
4. 收口：`--layer all` 全绿、后端/前端全量全绿、审计引证不受影响。

## 3. 方案（逐条，含缝与红-绿）

### 3.1 地图与展开同源（治 S3/P2/P5，取决 §8-A）

删掉 `MAP` heredoc，`--list` 改为**遍历各层的「计划段」**并逐层打印该层真实要跑的命令；
层来源（`api`/`web`/`all`）由 builder 记录（一个小并行数组，或把 builder 签名改成带 tag），
这样 `--list` 的每一行与 `--dry-run` 的每一行**逐字相同**。

**同源守卫（新缝，测试写在 `tests/test_verify_script.py`）**：

```
for layer in (unit, contract, coverage, deploy, fault, soak, scripts):
    assert 地图[layer] == dry_run 展开[layer]     # 相等，不是包含 —— P5 的自证问题一并消失
```

计划段要在**不安装依赖、不连数据库、不起 docker** 的前提下可渲染（现在 `--list` 是纯 heredoc，天然满足；改成渲染后必须保持）。

**代价（诚实说）**：`real` 层目前把 5 个步骤**内联在执行分支里**（不走 `cmds`），要让它进地图得把 `real_steps` 提升成顶层纯数据（约 20 行搬迁）；
其预检（`.env`/fixture/`curl /healthz`）保持在**执行路径**上，不得被 `--list` 触发。

### 3.2 顺序断言（S2）

`add_coverage` 读的 `coverage-api.json` 由 `add_api_unit` 写。加一条断言：`all` 的展开里，写数据那条命令必须**排在**判底线那条之前。
红-绿：先把 `add_coverage` 挪到 `add_api_unit` 之前 → 红；挪回 → 绿。

### 3.3 计数缓存删除（S4）

`AGENTS.md:61`、`docs/HANDOFF.md:74` 删掉「N 条命令」。
**决策依据**：本仓库的事实源是 `--list`／`--dry-run`（AGENTS.md 自述「只留看 `--list` 看不出来的几条」），
而 a 计划段渲染让地图逐字可信、b `--dry-run` 一直可数 —— 两条路都不需要把数字抄进文档。
（此项与 P8 的 `ca50da6` 同一条规矩，属回归性补漏。）

### 3.4 测试元组补 `coverage`（P1）

`test_list_exposes_every_layer` 的元组补 `coverage`（与 §3.1 的相等断言一起，元组本身随后可退化成「与真实层集合相等」）。
红-绿：先补断言（此时因 `--list` 已含 coverage 行，**不会**红）→ 见 §3.5 的变异证明补红。

> 诚实说明：P1 单独补元组是**不会变红**的（`--list` 早就有 coverage 行），所以它的「红」必须靠变异证明给：
> 把 coverage 行从地图里删掉 → 新断言红 → 恢复绿。

### 3.5 硬违规 + 台账号（S1/S5/P3）

1. `docs/HANDOFF.md:167` 改成**不带展开式的指针**（「钉住 `all` 的展开 ⊇ 各层展开（见 `tests/test_verify_script.py`）」），
   避免下次再抄一遍层名。红-绿：先让断言只认四层名字（现状）→ 指针化后由 §3.1 的相等断言接棒。
2. 新开 `docs/tickets/p9-verify-map-truth/PROBLEMS.md`，记 **P44**：
   「`e0d4fa4` 把 `--layer all` 补上 coverage 的那次改动，属 P31 同族但未上台账」。
   （编号已核对：现台账最高为 `p7-shared-rate-limit` 的 **P43**；P34–P43 已被占用。）

### 3.6 「与提案的偏差」（P4，闸门 3）

PR #23 的规格字面授权 = 「把 `test_all_layer...` 的元组扩成四层」；实际交付还包含 scripts 段 3 行 MAP 改名 + 2 条新测试，
**且已合并**（`fd79375`）。回退它属于行为回退、没有收益，故按闸门 3 **记偏差**（§7），不回滚。

### 3.7 `--scope` 语义（P6/S3，取决 §8-B）

- **(B1) 修**：`coverage)` 尊重 `--scope` —— `--scope web` 时该层无事可做（打印一行说明后 exit 0），`--scope api|all` 照旧。
  与 `unit`/`contract` 的既有语义一致（实测 `--layer unit --scope web` 只跑 vitest）。CI 侧零变化（CI 用的是 `--scope api`）。
- **(B2) 写明**：不改行为，在 `--list`/`--dry-run` 输出里把「coverage 只针对 api」写成显式注解，并补一条测试钉住该注解。

## 4. 明确不做

1. **不追 PR #23**：已合并，两轴结论中「已消解/已合并」的部分不再动（§7 记偏差即可）。
2. **不重构 verify.sh 的层定义**（不动 CI 调用的层与命令内容）——本轮只动「地图渲染」与三条机械项。
3. **不跑 `--layer real`**：zero 真机调用（预算守卫在，但本轮无必要）。
4. **不碰 `docs/architecture/` 与 `scripts/build_architecture_map.py`**（未跟踪，是别人的产物），也不 `git add -A`。

## 5. 交付物

| 文件 | 内容 |
| --- | --- |
| `scripts/verify.sh` | 计划段渲染 `--list`（删 MAP heredoc）；顺序断言；按 §8-B 落地 scope 语义 |
| `apps/api/tests/test_verify_script.py` | 地图 == 展开的相等断言；元组补 coverage；scope 语义断言 |
| `docs/HANDOFF.md` | 167 行指针化；74 行删计数 |
| `AGENTS.md` | 61 行删计数 |
| `docs/tickets/p9-verify-map-truth/` | 本 README ＋ `PROBLEMS.md`（P44）＋ `ACCEPTANCE.md`（红绿原始输出、未验证项、与提案的偏差） |
| PR | 见 §8-C |

## 6. 验收口径

1. 每条修复**红 → 绿各一次**，原始输出进 `ACCEPTANCE.md`（含修前红的那一次）。
2. `bash scripts/verify.sh --layer all` **ALL PASS**（条数届时实测填，不再写进文档正文）。
3. `uv run pytest tests/test_verify_script.py -q` 全绿；**变异证明**：手改任一层的 `--list` 行为 → 相等断言红 → 恢复绿。
4. 后端全量（带 `BR_*`，`--junitxml` 读数、0 skipped）＋ 前端全量 + ruff/eslint/tsc 干净。
5. `verify_audit_evidence.py --strict` 仍 `unverifiable: 0`（已核实：`docs/audit/units/*.json` 没有引用 `verify.sh`/`HANDOFF.md` 的行号，改了也不会牵动引证）。

## 7. 与提案的偏差（闸门 3，开工前先记）

1. **PR #23 超规格授权**（Spec #4）：规格只授权扩元组；实际含 scripts 段 3 行 MAP 改名与 2 条新测试。已合并，按偏差记录、不回滚。
2. 交接文档的 PR 状态已过期（OPEN → 已合并）：本阶段改从 `main` 切分支，与交接文档 §0 的「checkout 那条分支」不一致（理由见文首）。

## 8. 需要你拍板（三项）

**A. `--list` 是否改为由计划段生成（推荐 A2）**
- **A1 只打命令**：`--list` 每层打印真实命令，不再有 `api:`/`web:` 标签 → 输出形状变化最大，实现最简。
- **A2 保留标签**（推荐）：同 A1，但 builder 记录来源 scope，仍打印 `api:`/`web:`/`all:` → 对读者最友好，多一个并行数组。
- **A0 不改**：只把 MAP 的 5 条错行改对 → 治标，下次还会漂（P31 已发生过两次）。

**B. `--layer coverage --scope web` 的语义**
- **B1 修**（推荐）：尊重 `--scope`，与 unit/contract 一致；CI 零变化；属行为变更。
- **B2 写明**：不改行为，地图里显式写「coverage 只针对 api」并加断言。

**C. PR 形态**
- **C1 在本分支上开 PR #24**（推荐）：PR #23 已合并，它的 CI 记录不能再代表新提交。
- **C2 另切分支再开 PR**：与 C1 等价，仅分支名不同。

## 9. 诚实清单（本提案自身的未验证项）

1. §1.1 的漂移测量是**只读探针**，产物在 `var/`（不入库）；探针本身只比对命令行文本，不判断命令语义。
2. `real` 层进地图是**代码搬迁**，其展开届时只做 `--dry-run` 对照（不花钱、不验真机）。
3. CI 侧未跑（本地绿 + PR 由 GitHub 跑）；本机 `--layer all` 的读数届时填 ACCEPTANCE。
4. §3.4 的「补元组不会红」是**推理**（元组里只多一个已存在的层名），其红由 §3.5 的变异证明补。
5. 本轮不动 `--strict` 逐字级审计门槛的既有代价（D22），也未重锚任何引证。

