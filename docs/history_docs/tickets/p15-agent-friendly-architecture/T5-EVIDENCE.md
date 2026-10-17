# T5 证据（凭据泄漏门禁 verify_secrets.sh）

## 意图复述

- 我理解这票解决什么：F04（凭据以明文粘进对话/仓库）在环境里只有一条人读规则（AGENTS.md「真机凭据只进 gitignored `.env`」），没有任何会红的检查；本票把它落成第 2 层——一个既有判定、又对已知坏输入红过的门禁脚本，让「sk- 形假值/真值进了会被提交的文件」这件事由退出码而不是记性拦住。
- 我怎么做，到文件粒度：唯一新建 `scripts/verify_secrets.sh`（唯一写入路径）——脚本内一份 `PATTERNS` 真源 + 一个 `scan_to` 匹配器，`--selftest`（内嵌假阳性/假阴性样本）与默认仓库扫描共用这一份实现；默认扫描的文件集 = `git ls-files --cached --others --exclude-standard`（即会被提交的文件），再按票面排除 `docs/history_docs/` 与 `*.zstd`；判定全部走退出码（0 干净 / 1 命中 / 2 用法与环境错）。
- 我不做什么：不改任何现有文件（`.gitignore`、`scripts/verify.sh` 都不动，进层是 T8 的事）；不引入依赖（纯 bash + grep/awk/find/xargs/mktemp）；不写第二份扫描实现；真实凭据不入脚本、样本与输出（命中行只打印 文件:行号 + `[已打码]`）；不动工作区里 p14 在飞的未提交改动；不 commit / push / 开 PR。

## 红演示（实现之前：已知坏输入必红）

先在临时目录造一个已知坏样本（形如 `sk-` 前缀的假值），并证明**今天仓库里没有任何门禁会判它**——实现前的退出码读数如下。

## 红演示输出（实现之前）

```text
# 已知坏输入：一个假 sk- 值落在会被提交的文件里
$ grep -nE -e 'sk-[A-Za-z0-9-]{20,}[A-Za-z0-9]' "$TMP/leaked.env"
1:BR_DEEPSEEK_API_KEY=sk-[32 个 0：原文见下方红字说明]
exit=0

# 今天仓库里判它的门禁：不存在
$ bash scripts/verify_secrets.sh --selftest
exit=127

# 今天唯一入口 verify.sh 的计划里凭据检查条数
$ bash scripts/verify.sh --list | grep -ci secret
0
exit=1
bash: scripts/verify_secrets.sh: No such file or directory
```

读数：坏输入本身可判（`grep` 退出 0 且点名 `1:BR_DEEPSEEK_API_KEY=sk-…`），但当时仓库里没有任何门禁判它——脚本不存在（127），唯一入口 `verify.sh` 的计划里凭据检查 0 条（退出 1）。

## 实现期红-绿：从别的目录调用时的假绿（已实测并修掉）

```text
# 实现第一版后实测：从别的目录调用会假绿（仓库里明知有坏样本，却报干净）
$ cd /tmp && bash '/root/better resume/scripts/verify_secrets.sh'
repo=clean (0 hits in 600 files)
exit=0

# 加 cd "$ROOT" 之后，同一命令、同一坏样本：必须红
$ cd /tmp && bash '/root/better resume/scripts/verify_secrets.sh'
repo=dirty (1 hits in 600 files: 见上 文件:行号，内容已打码)
exit=1

# 样本删掉后恢复绿
$ bash scripts/verify_secrets.sh
repo=clean (0 hits in 599 files)
exit=0
```

> 证据里两处 `sk-` 假值原文（红演示 `grep` 读数的第 1 行、破坏演示的 `cat` 读数）已换成 `sk-[32 个 0…]`：把 32 个 0 的假值原样留在仓库里，门禁就会命中这份证据文件自己（验收 2 要求命中 0）。除此之外命令与输出逐字未改（`[已打码]` 是脚本自己的输出格式）。

## 验收命令原始输出

```text
=== 1) bash scripts/verify_secrets.sh --selftest ===
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
/tmp/tmp.mFqu02f2ca/bad/sample.env:2: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:3: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:4: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:5: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:6: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:7: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:8: [已打码]
/tmp/tmp.mFqu02f2ca/bad/sample.env:9: [已打码]
bad=detected (8/8 hits)
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 600 files)
selftest=PASS
exit=0

=== 2) bash scripts/verify_secrets.sh （扫仓库） ===
repo=clean (0 hits in 600 files)
exit=0

=== 3) 破坏演示：临时样本写成 sk- 前缀假值，同一命令内删除 ===
$ cat .verify-secrets-demo.tmp
BR_DEEPSEEK_API_KEY=sk-[32 个 0：原文见下方红字说明]
# 破坏演示的假值，跑完即删
$ bash scripts/verify_secrets.sh
repo=dirty (1 hits in 601 files: 见上 文件:行号，内容已打码)
exit=1
$ test -e .verify-secrets-demo.tmp && echo 还在 || echo 已删除
已删除

=== 4) 排除面读数（只数条数，不打印任何值） ===
$ git ls-files --cached --others --exclude-standard | grep -c '^\.env$'
0
$ grep -c '^BR_DEEPSEEK_API_KEY=sk-' .env
1
$ git ls-files | grep -c '^docs/history_docs/'
145
$ git ls-files | grep -c '[.]zstd$'
0
$ for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
shell syntax ok

=== 5) 变异证明：删掉 PATTERNS 里任一条，--selftest 必须红 ===
--- 变异：删掉含 'sk-[A-Za-z0-9-]{20,}[A-Za-z0-9]' 的那条模式（行数 195 -> 194）
$ bash scripts/.verify_secrets_mutated.tmp.sh --selftest
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
/tmp/tmp.LfCGx6QVx2/bad/sample.env:3: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:4: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:5: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:6: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:7: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:8: [已打码]
/tmp/tmp.LfCGx6QVx2/bad/sample.env:9: [已打码]
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 601 files)
exit=1
--- 变异：删掉含 '([Aa][Pp][Pp]' 的那条模式（行数 195 -> 194）
$ bash scripts/.verify_secrets_mutated.tmp.sh --selftest
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
/tmp/tmp.NmqqJZskvZ/bad/sample.env:2: [已打码]
/tmp/tmp.NmqqJZskvZ/bad/sample.env:3: [已打码]
/tmp/tmp.NmqqJZskvZ/bad/sample.env:4: [已打码]
/tmp/tmp.NmqqJZskvZ/bad/sample.env:5: [已打码]
/tmp/tmp.NmqqJZskvZ/bad/sample.env:9: [已打码]
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 601 files)
exit=1
$ test -e scripts/.verify_secrets_mutated.tmp.sh && echo 还在 || echo 已删除
已删除

=== 6) 收工时的写入面：只多出本票两个路径 ===
?? scripts/verify_secrets.sh

[stderr]
.verify-secrets-demo.tmp:1: [已打码]
bad=missed (7/8 hits: 有模式被删或被改，或样本行没被认出来)
selftest=FAIL
bad=missed (5/8 hits: 有模式被删或被改，或样本行没被认出来)
selftest=FAIL
```

验收对照：① `--selftest` 退出 0，输出含 `bad=detected`（8/8）与 `repo=clean`（0 hits in 600 files）✅ ② 默认扫仓库命中 0、退出 0 ✅ ③ 破坏演示退出 1 且点名 `.verify-secrets-demo.tmp:1`，样本在同一命令内删除 ✅

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 扫描范围取 `git ls-files --cached --others --exclude-standard`（会被提交的文件集合），而不是 `find` 全树 | 票面点名的 `.git/` `var/` `node_modules/` 本来就是 `.gitignore` 的产物，同一条口径顺带覆盖 `.cache/`（210M）`.pnpm-store/`（216M）`.venv/` `data/`；而且 `.env` 是 AGENTS.md 指定的唯一凭据通道，扫它等于误伤设计通道。实测旁证：`.env` 不在范围（0），但它确实装着 sk- 形真值（1） | 没写第二份「find 全树 + exclude-dir」实现；没扫 git 历史（只扫工作区会被提交的文件集） |
| 命中行只打印 `文件:行号 + [已打码]`，不回显命中原文 | 门禁把凭据原文抄进 CI 日志等于把泄漏二次外泄；票面（验收 3）只要求点名 文件:行号 | 没做 `--no-mask` 之类的调试开关；代价是路径含冒号会错位（本仓库无这种路径） |
| `PATTERNS` 只收高置信度形状，不做「任意 `*_KEY` 名 + 长值」的高熵规则 | 实测该规则在本仓库 4 处合法文本上误伤（`xingyun_factory.py:13` 的 `API_KEY_ENV = "XINGCHEN_API_KEY"` 等），而票面明确要求不误伤 `.env.example`；脚本内留了 `ponytail:` 注释与升级路径 | 没上 gitleaks 之类的新依赖，没做熵值判定 |
| `--selftest` 断言「坏样本命中数 == 样本非注释行数」，而不是「至少命中一条」 | 第一版自检只要求 `bad=detected`，删掉任一模式仍然绿（实测 6/7、5/7 都曾绿），等于没钉住模式集；改成逐行相等后「删模式必红」成立（证据 §5 变异 A/B） | 没为每条模式单独写期望值常量——期望值从样本自身数出来，加模式必须同时加样本行 |
| 坏样本的值由 `printf` 现场生成，PEM 头拆成两段字符串拼接 | 脚本自己也在扫描范围内：第一版正文里留着 PEM 头那串连续字面量，门禁命中自己（实测 `scripts/verify_secrets.sh:107`），会与验收 2 的「命中 0」互斥（本条也曾被门禁抓到过） | 没给脚本做自豁免（豁免清单是 T6 的口径，本票不开这个口子） |
| 脚本开头 `cd "$ROOT"` | `git ls-files` 给的是相对仓库根的路径，grep 在调用者 cwd 解析；未加时从 `/tmp` 调用会静默假绿（实测：仓库里有坏样本仍报 `repo=clean` 退出 0） | 没做 `--root` 参数（本票用不到） |
| 扫到 0 个文件时退出 2（不是绿） | 范围取 git 检出，「没东西可扫」必须与「干净」区分开，否则环境不对就假绿（P12 的同类） | 没做「扫描文件数低于阈值就报警」这类猜测性规则 |
| 破坏演示与变异证明各在仓库内写了一个临时文件（`.verify-secrets-demo.tmp`、`scripts/.verify_secrets_mutated.tmp.sh`），同一命令内删除 | 票面验收 3 要求「临时样本写入…同一命令内删除样本」，而样本必须落在扫描范围内才可能被判定 | 没动 `.gitignore`；收工时已核对两个临时文件都不存在（`test -e` 读数见证据） |

未验证项（诚实清单）：

- 没跑 `bash scripts/verify.sh --layer scripts`（该层跑 pytest 与审计结构检查，与本票无交集；把本脚本接进层是 T8 的范围）。
- 没验证 CI / pre-commit 接线——本票不接线（T8）。
- 扫描范围不含 git 历史：凭据若已进历史提交，本门禁看不见。
- 性能未在更大仓库上量过（本机 600 文件量级为秒内）；路径含冒号的情形未处理（本仓库无此路径）。
- 工作区里 p14 在飞的未提交改动没有被本票触碰；它们进入扫描范围是刻意的（`--others` 含未跟踪未忽略文件），本次读数为干净。

## 收工读数（证据文件落盘后的终态复跑）

```text
$ bash scripts/verify_secrets.sh
repo=clean (0 hits in 600 files)
exit=0

$ bash scripts/verify_secrets.sh --selftest
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:2: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:3: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:4: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:5: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:6: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:7: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:8: [已打码]
/tmp/tmp.wcbxHO5gdJ/bad/sample.env:9: [已打码]
bad=detected (8/8 hits)
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 600 files)
selftest=PASS
exit=0
```

> 第一次写这份证据时被门禁抓到两次：把 32 个 0 的假值与 PEM 头原样贴进 markdown，门禁就命中 `T5-EVIDENCE.md` 自己（`repo=dirty … T5-EVIDENCE.md:155`）——这正是它该做的事。两处改成 `sk-[32 个 0…]` 与「PEM 头那串连续字面量」的写法后才有了上面的读数；证据文件本身也在扫描范围内，这是刻意的。

文件计数口径：600 = `git ls-files --cached --others --exclude-standard` 去掉 `docs/history_docs/`（145 个受控文件）与 `*.zstd`（0 个）后的条数；它随别的票在同一工作区并行写入而变（本票开工时是 599，兄弟票新增脚本后是 600），不是固定值。
