# T10 证据（引证门禁围栏代码块豁免 verify_citations.sh）

## 意图复述

- 我理解这票解决什么：`scripts/verify_citations.sh` 现在把围栏代码块里的「文件:行号」也当引证判——票据自己贴的门禁原始输出、自检坏样本（T6/T7-EVIDENCE 的围栏输出块）因此被误抓成失败，T7-EVIDENCE 已把这条记为范围缺口。修的是解析范围：围栏内整行不判。
- 我怎么做，到文件粒度：只改 `scripts/verify_citations.sh`——加一个围栏掩码（行首允许缩进、以 ``` 或 ~~~ 切换围栏状态），把掩码后的文本交给既有 `grep -noE`（行数不变故行号不变）；`--selftest` 新增两个用例（围栏内的坏引证放过、围栏外同款抓住），并同步头注释的解析规则与自检汇总读数 4/4 → 6/6。
- 我不做什么：不改任何 markdown（含 T5-EVIDENCE 那类行内引证）；不豁免行内 code；不动 basename 兜底与歧义判定；不改退出码语义（0/1/2）；不引依赖；不 commit/push/开 PR；不碰 p14 在飞改动。

## 红：已知坏输入必红

开工前先跑两处红。

### 红 1：围栏内的坏引证与围栏外的一起进 FAIL

`/tmp` 临时树里两个样本，坏引证是同一条 `no/such/file.py`（行号 3）：`fenced-bad.md` 的形状是「第 1 行一条好引证、第 3 行与第 5 行是行首三反引号围栏、第 4 行是坏引证」，`unfenced-bad.md` 只有裸写的那一行。两跑都退出 1，第 4 行本该被放过：

```text
$ bash scripts/verify_citations.sh /tmp/tmp.nOFdrXylT4/fenced-bad.md
FAIL /tmp/tmp.nOFdrXylT4/fenced-bad.md:4 引证「no/such/file.py:3」：文件不存在（整仓没有 basename 为 file.py 的文件）
引证 2（直配 1，短名兜底 0）解析成功 1 失败 1
exit=1

$ bash scripts/verify_citations.sh /tmp/tmp.nOFdrXylT4/unfenced-bad.md
FAIL /tmp/tmp.nOFdrXylT4/unfenced-bad.md:1 引证「no/such/file.py:3」：文件不存在（整仓没有 basename 为 file.py 的文件）
引证 1（直配 0，短名兜底 0）解析成功 0 失败 1
exit=1
```

样本清单没有贴 `cat -n` 原文：反引号开头的行会把这份证据文件自己的围栏关掉，样本形状照上面 FAIL 行的行号即可复核。

### 红 2：新增的两个用例在旧实现下必须红

先只加用例与样本、不加掩码：

```text
$ bash scripts/verify_citations.sh --selftest
PASS 自检：好样本（直配 + 唯一短名） —— 退出 0
PASS 自检：不存在的路径 —— 退出 1
PASS 自检：行号越界 —— 退出 1
PASS 自检：同名多文件的短名 —— 退出 1
FAIL 自检：围栏内的坏引证放过 —— 期望退出 0，实得 1
      FAIL /tmp/tmp.Qy7W0yfDKI/fenced-ok.md:4 引证「no/such/file.py:3」：文件不存在（整仓没有 basename 为 file.py 的文件）
      引证 2（直配 1，短名兜底 0）解析成功 1 失败 1
PASS 自检：围栏外同款坏引证抓住 —— 退出 1
exit=1
```

stderr 另有一行 `自检失败：门禁没有按预期判定已知坏输入`。

## 改了哪几节

写入路径只有一个文件 `scripts/verify_citations.sh`：

- 头注释解析规则新增第 4 条（围栏代码块内整行不判；行内 code 不豁免），`--selftest` 的说明从「四个样本」改成「六个样本」；`usage()` 里同样的口径同步。
- 新增 `mask_fences()`：awk 按行首（允许缩进）的 ```/~~~ 切换围栏状态，围栏内的行输出空行——是掩码不是删行，行号必须与原文一一对应，否则 FAIL 行会指错行。
- 主循环取引证的口径从 `grep -noE -- "$CITE_RE" "$f"` 改成 `mask_fences "$f" | grep -noE -- "$CITE_RE"`（单文件 `grep -n` 读 stdin 一样从 1 编号）。
- `run_selftest()` 新增两个样本文件与两条 `case_expect`：围栏内坏引证放过（同时断言 `解析成功 1 失败 0`，证明是跳过围栏而不是整文件放行）、围栏外同款抓住（断言 `文件不存在`），汇总读数 4/4 → 6/6。旧用例的期望值零改动。
- 其余零改动：`resolve()` 的直配与 basename 兜底、歧义判定、白名单扩展名、退出码 0/1/2、`--root`。

## 验收命令原始输出

命令在仓库根跑，原样粘贴；`scripts/verify_citations.sh` sha256 = `7d023475dc2294b81d85cc675721672362c7705bc30ef3c590b2c1594623de4d`。

### 1（票面口径 1）：`--selftest` 全绿、用例数 6 > 4

```text
$ bash scripts/verify_citations.sh --selftest
PASS 自检：好样本（直配 + 唯一短名） —— 退出 0
PASS 自检：不存在的路径 —— 退出 1
PASS 自检：行号越界 —— 退出 1
PASS 自检：同名多文件的短名 —— 退出 1
PASS 自检：围栏内的坏引证放过 —— 退出 0
PASS 自检：围栏外同款坏引证抓住 —— 退出 1
自检通过 6/6：好样本绿；不存在路径 / 行号越界 / 同名多文件三种坏样本都被判失败；围栏内放过、围栏外同款抓住
exit=0
```

### 2（票面口径 2）：p15 全目录扫描

```text
$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/*.md
FAIL docs/tickets/p15-agent-friendly-architecture/T11-EVIDENCE.md:94 引证「T5-EVIDENCE.md:194」：短名 T5-EVIDENCE.md 歧义，命中 3 个：docs/history_docs/tickets/m6/T5-EVIDENCE.md docs/tickets/p14-web-redesign/T5-EVIDENCE.md docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md
FAIL docs/tickets/p15-agent-friendly-architecture/T11-EVIDENCE.md:100 引证「interview_engine/orm.py:72-95」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL docs/tickets/p15-agent-friendly-architecture/T11-EVIDENCE.md:108 引证「interview_engine/orm.py:116」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md:194 引证「T5-EVIDENCE.md:155」：短名 T5-EVIDENCE.md 歧义，命中 3 个：docs/history_docs/tickets/m6/T5-EVIDENCE.md docs/tickets/p14-web-redesign/T5-EVIDENCE.md docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md
引证 65（直配 47，短名兜底 14）解析成功 61 失败 4
exit=1
```

**这一条没到 0，是本票的偏差，且残留项全在本票写入路径之外**：

- T5-EVIDENCE.md 第 194 行：**行内 code 里的短引证、位于围栏之外**。票面口径 2 选定「只豁免围栏代码块、不豁免行内 code」，本票又红线禁止改 markdown，两条一起把它封在票外。它在语义上确实该判失败——`T5-EVIDENCE.md` 全仓有三个同名文件，短名本就歧义；真正的修法是把它挪进围栏、或写成唯一全路径，需要 markdown 的写入权属。
- T11-EVIDENCE.md 第 94 / 100 / 108 行：兄弟票在并发写入的在飞文件（本票开工时该文件还不存在，跑口径 2 时刚从无到有），不在本票写入路径内。

票面口径 2 预期的那部分已达成：T6-EVIDENCE 两条、T7-EVIDENCE 十五条、T5 自身第 194 行之外的输出块全部放过，见下面的前后对比。

### 3（票面口径 3）：两报告读数不变

```text
$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md docs/tickets/p15-agent-friendly-architecture/recall-report.md
引证 52（直配 44，短名兜底 8）解析成功 52 失败 0
exit=0
```

与 T7 的读数逐字相同：引证 52、成功 52、失败 0（recall 报告本身 0 条引证，52 全来自 pitfalls 报告）。

### 4（自带检查）：本证据文件自己也要过门禁

```text
$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/T10-EVIDENCE.md
引证 0（直配 0，短名兜底 0）解析成功 0 失败 0
exit=0
```

计数 0 说明本文件里的引证全在围栏块内、已被掩码；门禁不是空转——同一条命令对围栏外的文本照样判失败（第 2 组那几条 FAIL 就是证据）。

### 5（回归）：脚本语法与另两个门禁的主扫描

```text
$ for f in scripts/*.sh; do bash -n "$f" || echo "SYNTAX FAIL $f"; done; echo 'bash -n 全部通过'
bash -n 全部通过
$ bash scripts/verify_docs_hygiene.sh
扫描 496 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
exit=0
$ bash scripts/verify_secrets.sh
repo=clean (0 hits in 603 files)
exit=0
```

## 附带观察：p15 目录的前后对比（不计入票面验收）

把当前脚本的取数口径用 sed 还原成加掩码之前（`mask_fences "$f" | grep -noE -- "$CITE_RE"` → `grep -noE -- "$CITE_RE" "$f"`），同一分钟对同一批文件各跑一次：

```text
$ sed 's#mask_fences "$f" | grep -noE -- "$CITE_RE"#grep -noE -- "$CITE_RE" "$f"#' scripts/verify_citations.sh > "$d/old.sh"
$ cd '/root/better resume'   # 仓库根
$ d="$(mktemp -d)"; mapfile -t files < <(find docs/tickets/p15-agent-friendly-architecture -type f -name '*.md' | LC_ALL=C sort)   # 当时 23 个
$ bash "$d/old.sh" --root "$PWD" "${files[@]}"
引证 81（直配 52，短名兜底 11）解析成功 63 失败 18
exit=1
$ bash scripts/verify_citations.sh --root "$PWD" "${files[@]}"
引证 57（直配 45，短名兜底 11）解析成功 56 失败 1
exit=1
```

失败 18 → 1：17 条（T6-EVIDENCE 两条、T7-EVIDENCE 十五条）是围栏内的引文，第 18 条是 T5-EVIDENCE 第 194 行那条行内引证。总引证数 81 → 57 是口径变了——围栏内的行不再进计数，这正是本票要的。这段对比跑在 T11-EVIDENCE.md 出现之前，那批文件与这两个读数随兄弟票改动而变；口径 3 的 52 不受影响。

## 未验证项

- 票面口径 2 未达成（残留四条：T5-EVIDENCE 第 194 行那条行内短引证，加当时 T11-EVIDENCE 的三条）；本票写入路径只是脚本，修前者需要 markdown 写入权属，后者属兄弟票的在飞文件。
- 未接 `scripts/verify.sh --layer scripts`（T8 的写入路径），因此「接线后 CI 同一条命令的读数」未验证；`grep verify_citations scripts/verify.sh` 现为零命中。
- 围栏判定是与 `verify_docs_hygiene.sh` 同口径的朴素切换：不校验开闭配对、不区分围栏长度（四反引号同样切换）、未闭合围栏会把其后整篇判成围栏内；未验证嵌套/未闭合这两种形态（现树里没有真实输入需要它）。
- 未验证非 Linux 形态（脚本用 GNU `find -printf`、GNU `grep -E`）；未做性能断言，p15 目录 23 个文件秒级完成。
- `docs/tickets/p15-agent-friendly-architecture/` 被其他票并发写入：本文件的条数是命令输出那一刻的读数（口径 3 的 52 是稳定读数），会随兄弟票改动漂移——写作期间 T11-EVIDENCE.md 就是从无到有出现的。
- 未跑前端/后端测试（本票只动一个 bash 脚本）：回归只覆盖上面第 5 组的三条命令。

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 掩码实现 = `awk` 把围栏内的行换成空行，保持行数不变，再交给既有 `grep` | 失败行要打印 `文件:行号`，掩码一旦改行数，FAIL 行就指错行；换成删行或另建临时文件同样会动到行号口径 | 没改成「解析阶段带状态过滤」的重写（那会把 `grep` 的取数口径整个换掉，超出这票的范围） |
| 围栏判定复用 `verify_docs_hygiene.sh` 的头注释口径：行首允许缩进、``` 与 ~~~ 都切换状态 | 仓库里已经有一份围栏口径，第二份独立规则迟早会分叉；两处口径一致，读脚本的人不必记两套 | 没做围栏长度/嵌套/未闭合的规范级解析（现树没有这种输入，属于没人跑的规则） |
| 自检第二个用例的围栏起点用 `~~~`，闭合后再裸写同款坏引证 | 只用两个新用例的同时把另一种围栏标记也钉住；「闭合后仍判」比「换个文件再判一次」更能证明状态真的切回去了 | 没加第三个用例专门测 ``` 与 ~~~ 混用、也没测未闭合围栏 |
| 自检汇总读数硬编码成 6/6（沿用旧写法的 4/4） | 与既有脚本风格一致，改动只是一处数字 | 没改成由用例数自动累加（一个没人看的计数，维护成本大于收益） |
| 红 1 的样本清单不贴 `cat -n` 原文，只贴两跑输出并在正文描述样本形状 | 清单里行首的反引号会把这份证据文件自己的围栏提前关掉（本门禁把行首反引号当切换点），贴进去反而制造假引证 | 没为此放宽围栏判定 |
| 票面点名的待读文件之一是「T7-EVIDENCE.md 的『给 T8 的预警』」，该文件里没有这个标题 | 所指内容在 T7-EVIDENCE 的「实现决定交代」表里（T7 明写没做围栏代码块豁免、并给出理由），按这条理解执行即可，不必为对齐措辞去动 T7 的文件 | 没去 T7-EVIDENCE 里补一个同名小节（不在本票写入路径内） |
| 票面口径 2 的残留如实贴红、并在本文件里点名成因 | 红线（不改 markdown）与「不接受的自由度」（不豁免行内 code）在本票内互相封死；把 18 → 1 的读数与残留一起留档，比改口径或默不作声诚实 | 没顺手把 T5-EVIDENCE 第 194 行挪进围栏（不在写入路径内，且会动别人的在飞交付物）；没把行内 code 也豁免掉 |
