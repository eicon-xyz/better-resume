# T7 证据（引证解析门禁 verify_citations.sh）

## 意图复述

- 我理解这票解决什么：票据与验收包里的 `文件:行号` 引证是凭记忆写的，文件改名或行号漂移没人发现（P09）；这票把引证解析做成会判定的门禁——解析不了一律退出非 0，不是打印一句结论了事（D22）。
- 我怎么做，到文件粒度：新建 `scripts/verify_citations.sh`（bash + coreutils/grep/awk，无新依赖）——从输入的 markdown 抽出 `路径:行号`（行号支持 `起-止` 区间），路径先相对仓库根直配、直配不到按 basename 在整仓唯一命中兜底（零命中=文件不存在，多命中=短名歧义，两者都判失败），再核行号落在 `1..该文件行数`；内置 `--selftest` 用临时树造四个样本（好样本、不存在路径、行号越界、同名多文件）自证门禁真的会判失败；只写 `scripts/verify_citations.sh` 与本证据文件 `T7-EVIDENCE.md`。
- 我不做什么：不改任何报告与既有证据文件；不接 `scripts/verify.sh`（那是 T8 的写入路径）；不做 README 建议 9 的另一半「数字只能来自贴出的命令输出块」；不校验引证内容与所述是否相符（只判定路径与行号真的存在）；不读工作区未提交改动（p14 在飞，不碰）；不 `git commit`/`push`/开 PR；不引入依赖。

## 红：已知坏输入必红

实现前，票面验收命令在旧状态下就是红的（门禁还不存在）：

```text
$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md docs/tickets/p15-agent-friendly-architecture/recall-report.md
bash: scripts/verify_citations.sh: No such file or directory
exit=127
```

实现后，对真实形状的三种坏输入（样本写在 `/tmp/bad-citations.md`，不进仓库；文件里另留一条好引证做对照）：

```text
$ cat /tmp/bad-citations.md
正常引证 docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md:1
不存在路径 docs/nope/missing.py:3
行号越界 docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md:99999
短名歧义 __init__.py:1

$ bash scripts/verify_citations.sh /tmp/bad-citations.md
FAIL /tmp/bad-citations.md:2 引证「docs/nope/missing.py:3」：文件不存在（整仓没有 basename 为 missing.py 的文件）
FAIL /tmp/bad-citations.md:3 引证「docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md:99999」：行号 99999 越界（docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md 共 122 行）
FAIL /tmp/bad-citations.md:4 引证「__init__.py:1」：短名 __init__.py 歧义，命中 25 个：apps/api/scripts/__init__.py apps/api/src/better_resume/__init__.py apps/api/src/better_resume/ai_resilience/__init__.py apps/api/src/better_resume/chat/__init__.py apps/api/src/better_resume/conversation/__init__.py apps/api/src/better_resume/db/__init__.py apps/api/src/better_resume/http/__init__.py apps/api/src/better_resume/identity/__init__.py apps/api/src/better_resume/interview_engine/__init__.py apps/api/src/better_resume/interview_engine/corpus/__init__.py apps/api/src/better_resume/jobs/__init__.py apps/api/src/better_resume/llm_gateway/__init__.py apps/api/src/better_resume/llm_gateway/adapters/__init__.py apps/api/src/better_resume/media/__init__.py apps/api/src/better_resume/media/adapters/__init__.py apps/api/src/better_resume/observability/__init__.py apps/api/src/better_resume/resume_parser/__init__.py apps/api/src/better_resume/settings/__init__.py apps/api/tests/__init__.py apps/api/tests/ai_resilience/__init__.py apps/api/tests/contracts/__init__.py apps/api/tests/interview_engine/__init__.py apps/api/tests/llm_gateway/__init__.py apps/api/tests/media/__init__.py apps/api/tests/resume_parser/__init__.py
引证 4（直配 1，短名兜底 0）解析成功 1 失败 3
exit=1
```

三种坏输入各自进 FAIL 行、失败计数 3、退出 1——失败没有被降级成警告。

## 验收口径原始输出

命令在仓库根跑，原样粘贴（`scripts/verify_citations.sh` sha256 = `fe6c515936d007d3aa7465a65daf38a507a0cee6e03d90843aaf8c920b358582`）：

```text
$ bash scripts/verify_citations.sh --selftest
PASS 自检：好样本（直配 + 唯一短名） —— 退出 0
PASS 自检：不存在的路径 —— 退出 1
PASS 自检：行号越界 —— 退出 1
PASS 自检：同名多文件的短名 —— 退出 1
自检通过 4/4：好样本绿；不存在路径 / 行号越界 / 同名多文件三种坏样本都被判失败
exit=0

$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md docs/tickets/p15-agent-friendly-architecture/recall-report.md
引证 52（直配 44，短名兜底 8）解析成功 52 失败 0
exit=0

$ bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/T1-EVIDENCE.md docs/tickets/p15-agent-friendly-architecture/T2-EVIDENCE.md
引证 0（直配 0，短名兜底 0）解析成功 0 失败 0
exit=0
```

票面三条读数对上：引证 52、解析成功 52、失败 0、退出 0（44 直配 + 8 短名兜底）；`--selftest` 退出 0；T1/T2-EVIDENCE 扫描退出 0。

## 附带观察（不计入本票验收）

`docs/tickets/**/*.md` 全树快照（2026-10-17T04:12:59Z；p15 目录正被其他票并发写入，数字只是那一刻的读数）：

```text
FAIL docs/tickets/p11-resume-driven-questions/README.md:23 引证「orm.py:72-95」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL docs/tickets/p11-resume-driven-questions/README.md:25 引证「orm.py:166-168」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL docs/tickets/p11-resume-driven-questions/README.md:28 引证「orm.py:47-65」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL docs/tickets/p12-intent-alignment/ACCEPTANCE.md:69 引证「settings_config.py:8」：文件不存在（整仓没有 basename 为 settings_config.py 的文件）
FAIL docs/tickets/p15-agent-friendly-architecture/T6-EVIDENCE.md:48 引证「docs/bad-sample.md:1」：文件不存在（整仓没有 basename 为 bad-sample.md 的文件）
FAIL docs/tickets/p15-agent-friendly-architecture/T6-EVIDENCE.md:49 引证「docs/bad-sample.md:2」：文件不存在（整仓没有 basename 为 bad-sample.md 的文件）
引证 364（直配 247，短名兜底 111）解析成功 358 失败 6
fulltree exit=1
```

剩下 6 条不是门禁的缺陷：p11 `README.md` 的 3 条 `orm.py` 是**真歧义**（三个同名 orm.py，短名兜底本就该判失败）；p12 `ACCEPTANCE.md` 的 `settings_config.py` 在本仓不存在；T6-EVIDENCE 的两条是那份自检自己写的坏样本。四处都不在本票写入路径内，本票不改。

## 未验证项

- T1-EVIDENCE.md / T2-EVIDENCE.md 的退出 0 是「0 条引证」的空绿：两份文件里没有 `文件:行号` 形状的引证，这条验收不构成解析正确性的证据。
- 全票据树扫描不在验收口径内，且 p15 目录正被其他票并发写入；上表 364/358/6 只是 2026-10-17T04:12:59Z 的快照，未复核那 6 条的业务真伪（其中 4 条指向别的票，本票无权改）。
- 未验证非 Linux 形态：脚本用了 GNU `find -printf`，macOS/BSD 的 find 不认（本仓库只跑 Linux/WSL/Docker）。
- 未验证大输入性能（未做计时断言）；实测 364 条引证的全树扫描在本机秒级完成。
- 未跑 ruff/lint（不适用）；只跑了 `bash -n scripts/verify_citations.sh` 与 T8 待接的 `for f in scripts/*.sh; do bash -n` 同款语法检查。
- 未接 `scripts/verify.sh --layer scripts`（T8 的写入路径），因此本票未验证「接线后 CI 同一条命令仍然绿」。

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 短名兜底的索引 = 整仓 `find` 扫描，跳过依赖与生成物目录（`.git`/`node_modules`/`.venv`/`__pycache__`/`.cache`/`dist`/`coverage`/`htmlcov` 等） | 票只写「短名按唯一 basename 解析」，没写索引从哪来。实测 gitignored 的 `apps/web/coverage/base.css` 会把 p14 里正常的 `base.css:18-21` 误判成歧义：判红与否取决于本机跑没跑过前端 coverage，正是 P12 说的「索引成了运行环境的隐式入参」 | 没改成 `git ls-files --cached --others --exclude-standard`（那要求 `--root` 落在 git 工作树里，自检的临时树就用不了；已在脚本里留 `ponytail:` 注释写明升级路径）；没预先 prune `var/`（实测 1277 个文件与 docs/tickets 引用的 60 个 basename 零撞名，不凭空加假设） |
| 引证 = 白名单扩展名（py/ts/tsx/js/jsx/md/json/sh/yaml/yml/sql/css/html）+ `:行号`；行号可写 `起-止` 区间，区间算 1 条 | 报告里既有 `xunfei_ast.py:238-239` 这种区间，也有 `127.0.0.1:5433` 这种「点号+数字」的假引证——没有扩展名白名单时后者会被当成扩展名 `1` 扫进来，52 的读数就不成立 | 没做围栏代码块豁免（两份被扫报告里没有围栏内的引证，加了反而是没人跑的规则）；没做建议 9 的另一半「数字只能来自贴出的命令输出块」；没做引证内容与所述是否相符的语义核对 |
| `--selftest` 除退出码外还断言输出关键词（`文件不存在` / `越界` / `歧义`），并要求好样本退出 0 | 只看退出码时，一个因别的原因崩掉的门禁也能「自检通过」；关键词把「判失败」与「失败得对」分开，好样本则挡住「永远退出 1 也算通过」 | 没扩样本面（CJK 路径、符号链接 `--root`、空文件等形态未进自检） |
| 失败行带输入文件的第几行（`FAIL 文件:行号 引证「…」：原因`）；成功时打印 `引证 N（直配 X，短名兜底 Y）解析成功 N 失败 0` | 票要求「验收不许手写条数当读数」——数字必须由门禁自己算出；直配/短名两列让「basename 兜底真的生效（8 条）」可机械读，不必靠人复述 | 没逐条打印成功的引证（52 行噪声；失败才需要看） |
| 退出码：0 全部解析成功 / 1 有引证解析失败 / 2 用法或输入错误；额外开关只有 `--root`（供自检指向临时树） | 与仓库既有验证脚本同语义（`verify_mutation.sh` 的 0/1/2），T8 接线时不必再翻译 | 没做 `--json`/`--quiet`/豁免标记等开关（票没点名，也没有豁免需求） |
| 脚本内注释与输出用简体中文 | `AGENTS.md` 规定注释与文档一律简体中文；输出会被贴进验收包给人读 | 没顺手改既有英文脚本（不在本票写入路径内） |
