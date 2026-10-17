# T25 验收证据：远端状态只读可见

## 意图复述

1. 远端 PR 状态（建没建、base 对不对、合到哪）只存在于人的脑子与对话里，智能体读不到（recall-report [F18]）；缺的是一条只读、可判定的读法。
2. 本票只加一条读法：`bash scripts/pr_state.sh` 现读当前分支的 PR 状态（number/state/base/head；该分支没有 PR 就写「无 PR」），gh 缺失/未登录时非 0 且点名原因——两种情形绝不混成同一种读数；不写远端、不引依赖、不加第二个写入路径。
3. 先红后绿：先跑同一批验收命令记录红（脚本不存在；朴素的 `gh pr view` 在无 PR 分支上与故障同为退出 1），再落脚本并让 `--selftest` 与真跑都绿。

## 红演示：落脚本之前

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH"
bash scripts/pr_state.sh; echo "exit=$?"
bash scripts/pr_state.sh --selftest; echo "exit=$?"
grep -nE "gh .*(create|merge|close|edit|push)" scripts/pr_state.sh; echo "grep exit=$?"
gh pr view --json number,state,baseRefName,headRefName; echo "gh pr view exit=$?"
```

原始输出（stdout 逐字，stderr 附在后）：

```text
$ bash scripts/pr_state.sh
exit=127
$ bash scripts/pr_state.sh --selftest
exit=127
$ grep -nE "gh .*(create|merge|close|edit|push)" scripts/pr_state.sh
grep exit=2
$ gh pr view --json number,state,baseRefName,headRefName   # 朴素读法
gh pr view exit=1

stderr：
bash: scripts/pr_state.sh: No such file or directory
bash: scripts/pr_state.sh: No such file or directory
grep: scripts/pr_state.sh: No such file or directory
no pull requests found for branch "p14-web-redesign"
```

红的样子：三条验收命令全部落空（脚本不存在，退出 127 / grep 2）。第四条是同一件事的现状读数——朴素的 `gh pr view` 在「这条分支没有 PR」时退出 1，与「未登录 / 网络坏」同码，智能体只能去猜 stderr 文本。绿起来之后同一条分支的读数是「无 PR」+ 退出 0（见 §3）。

## 绿：落脚本之后

以下读数来自脚本落定后的运行；gh 已登录且可连 GitHub。

### 1 语法

```bash
cd '/root/better resume'
bash -n scripts/pr_state.sh; echo "exit=$?"
```

```text
exit=0
```

### 2 内置自检

```bash
bash scripts/pr_state.sh --selftest; echo "exit=$?"
```

```text
ok   有 PR：退出码：0
ok   有 PR：正文：number=31 state=OPEN base=main head=p15-agent-friendly-architecture
ok   无 PR：退出码：0
ok   无 PR：正文点名「无 PR」：yes
ok   调用失败：退出码：1
ok   调用失败：点名 gh 未登录：yes
ok   gh 缺失：退出码：2
ok   gh 缺失：点名找不到可执行文件：yes
ok   不在 git 仓库：退出码：2
ok   不在 git 仓库：点名原因：yes
selftest: 10 项断言，失败 0 项
exit=0
```

### 3 真实 gh：当前分支（p14-web-redesign，无 PR）

```bash
bash scripts/pr_state.sh; echo "exit=$?"
```

```text
无 PR：分支 p14-web-redesign 在远端没有 PR
exit=0
```

### 4 只读自证

```bash
grep -nE "gh .*(create|merge|close|edit|push)" scripts/pr_state.sh; echo "grep hit exit=$?"
grep -nE "gh (pr|api|auth|repo|run|release)" scripts/pr_state.sh; echo "exit=$?"
```

```text
grep hit exit=1
37:# 唯一的远端读法：gh pr list 是 GET，本脚本里不存在任何远端写动作。
92:printf 'To get started with GitHub CLI, please run: gh auth login\n' >&2
131:  contains "调用失败：点名 gh 未登录" "gh auth login" "$out"
exit=0
```

第一条 0 命中（退出 1 即 grep 无匹配）。第二条是正面清单：脚本里唯一的远端调用是 `scripts/pr_state.sh:39` 的 `pr list`（GET）；另两处是自检里假 gh 的报错文本与断言字符串，不发起调用。

### 5 真实 gh + 真实 PR（当前分支没有 PR，用同一条命令指向有 PR 的分支）

脚本读的是当前分支，而当前分支 p14-web-redesign 没有 PR；「有 PR」的真实读数用 `pr_line` 的同一条 gh 命令、只把 `--head` 指向有 PR 的分支取：

```bash
gh pr list --head p11-resume-driven-questions --state all --json number,state,baseRefName,headRefName --jq 'sort_by(.number) | last | select(.) | "number=\(.number) state=\(.state) base=\(.baseRefName) head=\(.headRefName)"'; echo "exit=$?"
```

```text
number=26 state=MERGED base=main head=p11-resume-driven-questions
exit=0
```

### 6 detached HEAD（隔离临时仓库，不碰工作区）

```bash
t="$(mktemp -d)"; cd "$t"
git init -q -b main . && git -c user.email=a@b -c user.name=a commit -q --allow-empty -m init && git checkout -q --detach
BR_PR_STATE_GH=/bin/true bash '/root/better resume/scripts/pr_state.sh'; echo "exit=$?"
```

```text
pr_state: HEAD 处于 detached 状态，没有分支名可查 PR      ← stderr
exit=2
```

### 7 自检不留临时目录

```bash
before="$(ls -d /tmp/tmp.* 2>/dev/null | wc -l)"; bash scripts/pr_state.sh --selftest >/dev/null; after="$(ls -d /tmp/tmp.* 2>/dev/null | wc -l)"; echo "tmp dirs before=$before after=$after"
```

```text
tmp dirs before=11 after=11
```

### 8 变异证明：自检真的钉住「无 PR 不许写成故障」

```bash
cd '/root/better resume'
bash scripts/verify_mutation.sh --test "bash scripts/pr_state.sh --selftest" --file scripts/pr_state.sh \
  --find 'printf "无 PR：分支 %s 在远端没有 PR\n" "$branch"' \
  --replace 'printf "pr_state: gh 调用失败（无 PR）\n" >&2; exit 1'
```

```text
== 1/3 baseline: the test must PASS on the untouched implementation ==
selftest: 10 项断言，失败 0 项

== 2/3 mutate: apply --find/--replace to scripts/pr_state.sh ==
mutated 1 occurrence in scripts/pr_state.sh

== 2/3 red: the test must FAIL on the mutated implementation ==
FAIL 无 PR：退出码：期望 [0] 实际 [1]
FAIL 无 PR：正文点名「无 PR」：期望 [yes] 实际 [no]
selftest: 10 项断言，失败 2 项
ok: mutation was caught

== 3/3 restore: the test must PASS again ==
restored: scripts/pr_state.sh sha256=9eedbf93053a27ac…
selftest: 10 项断言，失败 0 项

PASS: baseline green -> mutation red -> restored green (scripts/pr_state.sh)
```

### 9 卫生门禁与写入范围

```bash
bash scripts/verify_docs_hygiene.sh; echo "docs_hygiene exit=$?"
bash scripts/verify_secrets.sh; echo "secrets exit=$?"
for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
sha256sum scripts/pr_state.sh
find scripts 'docs/tickets/p15-agent-friendly-architecture' -type f -newermt '2026-10-17 14:36' | sort
```

```text
扫描 532 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
docs_hygiene exit=0
repo=clean (0 hits in 643 files)
secrets exit=0
shell syntax ok
9eedbf93053a27ac674cefdc45061f9894059360ffb778eb7fa82a283de4cd61  scripts/pr_state.sh
```

`find` 一栏里属于本票的是 `scripts/pr_state.sh` 与 `T25-EVIDENCE.md`；同目录其余文件是并行票（T24 / T26 等）的写入，本票未碰。

## 实现决定交代

| 决定 | 为什么这么定 | 放弃的替代 / 代价 |
| --- | --- | --- |
| 「无 PR」退出 0、正文写「无 PR」；gh 调用失败退出 1、点名原因 | 票面只要求坏路径非 0；「读到了，只是没有」不是故障，把它做成非 0 会让无 PR 分支上的读数看起来像失败 | 无 PR 也非 0（更保守的闸门语义）；放弃——本脚本是状态读数，不是闸门 |
| 用 `gh pr list --head <分支> --state all`（`scripts/pr_state.sh:39`）而不是 `gh pr view` | view 在「没有 PR」与「未登录 / 网络坏」下同为退出 1，只能靠 stderr 文本区分；list 用 `[]` + 退出 0 表达「没有」，`--state all` 才看得到 MERGED（[F18] 问的就是「合到哪」） | 两次调用（list 探存在、view 取详情）；放弃——多一次网络往返换不来新信息 |
| 同一分支多个 PR 时取编号最大者：`--jq 'sort_by(.number) \| last \| select(.) \| …'`（`scripts/pr_state.sh:41`） | 不依赖 gh 的默认排序；空数组经 `select(.)` 得空输出，正好落到「无 PR」分支 | 不排序直接取首条；放弃——重开过 PR 的分支上可能报出旧的已合并 PR |
| 环境不满足（无 git / 不在仓库 / detached HEAD / 无 gh）退 2 并各自点名（`scripts/pr_state.sh:46-56`）；gh 调用失败退 1，原因原样带上 gh 的 stderr（`scripts/pr_state.sh:68-69`） | 错误语义要分得开「你这边环境不对」与「远端不让我读」；未登录的具体措辞由 gh 自己给，不自己猜分类 | 解析 stderr 关键词再分类；放弃——文本匹配脆，且会把猜测写成结论 |
| 注入点 `BR_PR_STATE_GH`（默认 PATH 里的 gh，`scripts/pr_state.sh:18`） | 自检要覆盖「有 PR / 无 PR / 调用失败 / gh 缺失」四种读数又不能碰网络；它同时是把非 PATH 安装的 gh 指进来的方式 | 用 PATH 前置假 gh 目录；放弃——「gh 缺失」那一例还得另造一个没有 gh 的 PATH |
| 不缓存：每次调用现读远端 | 票面「不许缓存远端状态」；缓存住的 PR 状态会与远端漂移 | 无 |
| 自检里「不在 git 仓库」断言在临时目录落进工作树、或本机没有 git 时打印 skip（`scripts/pr_state.sh:137-144`） | 这两种环境下该断言不成立；跳过必须可见，不许静默通过 | 删掉这条断言；放弃——会少覆盖一条点名路径 |
| 不做：HANDOFF 生成物 `--check`（属会话工具链）、不接进 `verify.sh`（唯一写入路径只有本文件）、不写远端（硬规则 1） | 票面明列 | 无 |

退出码 0 / 1 / 2 的分配是票面未指定的自由度，按上表前两条定，并写进脚本头部（`scripts/pr_state.sh:12-13`）。

## 与提案的偏差

无。实现全部落在票面「唯一写入路径」（`scripts/pr_state.sh`）与本证据文件内。

## 过程交代：一次库外写入（已清理）

第一次跑 `--selftest` 时，`selftest` 仍把临时目录赋给局部变量 `tmp`，而 `cleanup` 由 EXIT trap 触发，此刻局部变量已出栈：`rm -rf ""` 静默无效，同时三个假 gh 被写到 `/gh-open`、`/gh-none`、`/gh-fail`（仓库外）。改为全局 `selftest_tmp`（`scripts/pr_state.sh:20,70-71`）后，三个文件已 `rm -f` 清理（`ls` 复核报 No such file），临时目录不再泄漏（§7 读数 11→11）。仓库内的写入仍只有脚本与本证据文件两个。
