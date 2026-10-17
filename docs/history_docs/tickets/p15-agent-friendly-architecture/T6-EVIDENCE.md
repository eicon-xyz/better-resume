# T6 证据：历史叙事门禁 verify_docs_hygiene.sh

## 意图复述

- 我理解这票解决什么：AGENTS.md 硬规则 2（文档与注释只描述当前状态）现在只靠人工规则拦，智能体往文档/注释里写 `第 N 轮修复`、`已废弃` 这类历史叙事时没有可红的检查；本票把它落成一条能进 `verify.sh` 的静态门禁。
- 我怎么做到文件粒度：新建唯一脚本 `scripts/verify_docs_hygiene.sh`——顶部一个禁词数组（逐条注释为何不误伤）+ 围栏代码块/行内 code 豁免规则 + 脚本内按原文精确匹配的 AGENTS.md 豁免清单 + `--selftest`（阳性必红、阴性必绿）；扫描 docs/（除 docs/history_docs/）、skills/、AGENTS.md、GLOSSARY.md、CODING_STANDARDS.md 与 apps/ 源码，本票证据写进本文件。
- 我不做什么：不改任何现有文档（豁免只写在脚本里）、不引入依赖、不接 `verify.sh`、不做整文件/整目录豁免（docs/history_docs/ 除外）、不 commit/push、不碰 p14 未提交改动。

## 红绿纪律（先红后绿）

### 红：门禁不存在时，票里的验收命令直接失败

```text
$ cd '/root/better resume' && bash scripts/verify_docs_hygiene.sh --selftest; echo "exit=$?"
exit=127
bash: scripts/verify_docs_hygiene.sh: No such file or directory
```

（stdout/stderr 分属两个流，这里按捕获顺序拼接。）

### 红（变异）：删掉一条禁词，`--selftest` 转红

副本放 /tmp（不写仓库），删掉 `曾经踩过` 那条禁词后跑自检：

```text
$ bash "$d/scripts/verify_docs_hygiene.sh" --selftest; echo "exit=$?"
ok   [必红] 84f622b 手测轮次样本：命中 2 处
ok   [必红] 禁词 之前是：命中 1 处
ok   [必红] 禁词 第 N 轮：命中 1 处
ok   [必红] 禁词 已废弃：命中 1 处
ok   [必红] 禁词 已作废：命中 1 处
ok   [必绿] CODING_STANDARDS 不适用模板措辞
ok   [必绿] 围栏代码块内引证
ok   [必绿] 行内 code 内引证
ok   [必红] 豁免只认原文：改一个字符即失效：命中 1 处
exit=1
FAIL [必红] 禁词 曾经踩过：0 命中，禁词集漏了这类写法
FAIL [必绿] AGENTS.md 三行原文：命中 0 处、豁免 4 处（应为 0 与 5）
自检失败：2/11 个用例不符预期
```

缺的那条 ok 行正是被删的禁词；stdout 与 stderr 分属两个流，顺序按各自到达。

### 红（坏输入进主扫描）：把 84f622b 样本放进 docs/ 后主扫描退出 1

```text
$ bash "$d/scripts/verify_docs_hygiene.sh"; echo "exit=$?"
HIT	docs/bad-sample.md:1: 命中「第[[:space:]]*(N|[0-9]+)[[:space:]]*轮」→ **P1-A 浏览器手测已完成**（第 3 轮通过，2026-09-17）：…
HIT	docs/bad-sample.md:2: 命中「第[[:space:]]*(N|[0-9]+)[[:space:]]*轮」→ | 第 1 轮 | 2026-09-15 | §1 步骤 1–4 …
exit=1
```

`$d` 是 /tmp 下的最小仓库镜像（scripts/ 副本 + 真实 AGENTS.md 符号链接 + docs/ + skills/ + GLOSSARY/CODING_STANDARDS 副本），只用于红演示，跑完即删。

## 改了哪几节

- 新建 `scripts/verify_docs_hygiene.sh`：顶部一个禁词数组（5 条，逐条注释为什么不误伤）+ 围栏代码块/行内 code 豁免规则（写成注释并由自检覆盖）+ 脚本内按原文精确匹配的 AGENTS.md 三行豁免清单（每条带理由）+ `--selftest`（11 个用例）。
- 新建本证据文件 `T6-EVIDENCE.md`（票要求的 `## 意图复述` 与 `## 实现决定交代`）。
- 既有文档零改动（红线）：豁免只写在脚本里；未接 `verify.sh` / CI（票未要求，接线属 T8）。

## 验收命令原始输出

### `bash scripts/verify_docs_hygiene.sh --selftest`

```text
$ cd '/root/better resume' && bash scripts/verify_docs_hygiene.sh --selftest; echo "exit=$?"
ok   [必红] 84f622b 手测轮次样本：命中 2 处
ok   [必红] 禁词 之前是：命中 1 处
ok   [必红] 禁词 第 N 轮：命中 1 处
ok   [必红] 禁词 已废弃：命中 1 处
ok   [必红] 禁词 曾经踩过：命中 1 处
ok   [必红] 禁词 已作废：命中 1 处
ok   [必绿] CODING_STANDARDS 不适用模板措辞
ok   [必绿] 围栏代码块内引证
ok   [必绿] 行内 code 内引证
ok   [必绿] AGENTS.md 硬规则 2 三行原文按清单豁免（3 行共 5 个禁词命中）
ok   [必红] 豁免只认原文：改一个字符即失效：命中 1 处
自检通过：11/11 个用例符合预期
exit=0
```

### `bash scripts/verify_docs_hygiene.sh`（命中 0、退出 0）

```text
$ cd '/root/better resume' && bash scripts/verify_docs_hygiene.sh; echo "exit=$?"
扫描 492 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
exit=0
```

### 异目录调用（不依赖 cwd）

```text
$ cd /tmp && bash '/root/better resume/scripts/verify_docs_hygiene.sh'; echo "exit=$?"
扫描 492 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
exit=0
```

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 「源码注释」的扫描面定为 `apps/api/src`、`apps/api/tests`、`apps/web/src`，不含 `scripts/` | 门禁脚本自身必须含禁词表、豁免原文与自检样本，把 scripts/ 纳入扫描等于要求门禁打自己；应用源码注释都在 apps/ 下 | 没扫 `scripts/`、`deploy/`、`apps/api/scripts`、根目录 README 等 `*.md` |
| 禁词只留 5 条，不收 `本次改动`、`改动前/后`、`本次修复` | 这些说法在现仓库有合法用法：CODING_STANDARDS §6 的「不适用」模板（`本次改动没有 X`）、p12 票据对规则的引用、p14 证据里的改前改后叙述；宽松模式实测误命中 21 处 | 不追求拦全部历史叙事：p14 证据里的 `改动前` 类叙述仍是已知漏报 |
| 行内 code 用「剥掉反引号片段再判」实现豁免，围栏块整行跳过，缩进代码块不豁免 | 票点名要覆盖围栏块与行内 code；缩进块在本仓库几乎不用，为它加嵌套规则得不偿失 | 没处理 HTML `<pre>`、缩进代码块、转义反引号 |
| 豁免 = 相对路径 + 去首尾空白后整行原文精确相等（3 条，按行）；命中计数按禁词出现次数（三行共 5 处） | 原文一改即失效、门禁自动转红，避免按关键词模糊放行；空白归一化让缩进不成为匹配噪音 | 未对「未被使用的豁免条目」报警：该行不再含禁词时豁免自然失效，不构成假阴性 |
| 扫描集为空或任一扫描根缺失时 `die`（退出 2） | 空/缩水的扫描集 = 静默绿灯，比红更贵 | 未校验扫描文件数下限（只保证根存在且非空） |
| 主扫描汇总数字运行期统计（本次 492 个文件），不写死 | 文档会增减，写死数字立刻过期 | 不提供 JSON/机器可读输出 |
| 自检断言「AGENTS.md 三行原文：0 命中 + 5 处豁免」，并用「改一个字符即红」证明精确匹配 | 只断言绿无法区分「被豁免」与「根本没扫到」 | 不搭变异测试框架，仍用临时副本 + `sed` 的最小演示 |

## 未验证项

- 未在 CI 跑过：脚本未接 `verify.sh --layer scripts` 与 GitHub Actions（票未要求；按建议 7 属于 T8 接线范围）。
- 兼容性只在本机验过：GNU bash 5.1.16 / GNU awk 5.1.0 / GNU grep 3.7 / GNU sed 4.8；未验 busybox、macOS BSD 工具链与 mawk。
- 历史归档 `docs/history_docs/` 按票整目录排除，未扫描；其它分支/未合并票据的文档也未纳入。
- 492 个文件与 5 处豁免是本次运行时的读数；文档随后续提交增减，数字会变（不写死正是为此）。
- 未验证真实「人类写作者」的措辞覆盖面：禁词集只对票点名的样本与当前全树负责，不能证明覆盖全部历史叙事形态。

