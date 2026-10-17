# T18 证据：测试 hermetic 门禁 + 交付验证技能（含 P15-6 SKILL.md 同步）

## 意图复述

- 我理解这票解决什么：p15 建议 11 的「环境半边」与建议 12/14 的第 3 层——「测试必须 hermetic」目前只是 AGENTS.md 的人读规则（P12 两次被干净 shell 抓出来），要把它做成会判定的门禁；「交付文案返工 / AI 味 / 中文 / 图·HTML 出口 / 改动说明格式」（F08/F09/F10/F14/F16）目前只在对话里逐条口头打回，要落成一个可被引用的交付验证技能（single source），AGENTS.md/CODING_STANDARDS 只放指针；同时把 T12 已改掉的 is_configured async 语义在 skills/modules/llm_gateway/SKILL.md 里同步成 config_status 快照（P15-6）。
- 我怎么做，到文件粒度：新增 scripts/verify_hermetic.py（判据：用例读隐式环境变量/代理/PATH/本机绝对路径，命中即红；自带 --selftest 已知坏样本必红 + 豁免按原文精确匹配 + 删判据即自检失败），在 scripts/verify.sh 的 build_scripts() 加它两行接线（--selftest 与全量扫描）；新增 skills/verify-delivery/（SKILL.md 五节：文案判据/AI 味词表/中文/图·HTML 出口/改动说明格式 + check_copy.py 机械判据 helper 与 --selftest）并把它的自检接进同一层；把 skills/modules/llm_gateway/SKILL.md 的 is_configured 段刷成 config_status 快照语义。
- 我不做什么：不改 AGENTS.md / CODING_STANDARDS.md 正文（只报指针清单）；不扩大写入路径（只写 scripts/、skills/ 与本证据文件）；不动 p14 在飞改动；不引依赖（helper 只用标准库）；不 commit/push/开 PR；不把技能写成散文，也不把既有规则原文抄进技能。

## 红-绿（先红后绿）

门禁与技能都是新建件，红演示做了两处：**门禁在真测试树上报红并点名到行**，以及**判据被改坏时自检必须红**。
两处都在本票写入路径内完成，红完逐字节还原（sha256 比对）。

### 红 1：门禁在真测试树上报红（摘掉 H2 豁免）

```bash
cd '/root/better resume'
cp scripts/verify_hermetic.py /tmp/t18-hermetic.bak
python3 - <<"PY"
from pathlib import Path
p = Path("scripts/verify_hermetic.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
k = next(i for i, line in enumerate(lines) if "test_openai_compat.py" in line)
del lines[k - 2 : k + 3]                      # 摘掉 EXEMPTIONS 的第一条
p.write_text("".join(lines), encoding="utf-8")
PY
python3 scripts/verify_hermetic.py; echo "EXIT=$?"
cp /tmp/t18-hermetic.bak scripts/verify_hermetic.py
sha256sum scripts/verify_hermetic.py /tmp/t18-hermetic.bak
```

```text
HIT [H2] apps/api/tests/llm_gateway/test_openai_compat.py:94 遍历 ambient 代理变量（无键名地读环境）
    原文：for name in [key for key in os.environ if key.lower().endswith("_proxy")]:
EXIT=1
e6477f910d9b91d9fd8d8786514941f8704883f39ba9c7675ad24a953aaf617a  scripts/verify_hermetic.py
e6477f910d9b91d9fd8d8786514941f8704883f39ba9c7675ad24a953aaf617a  /tmp/t18-hermetic.bak
verify_hermetic: 命中 1 处隐式环境依赖；判据见脚本顶部。 确属必要请进 EXEMPTIONS（按原文精确匹配 + 写清为什么），不要放宽判据。
```

判据本身没动，红是「真测试树上有这一处隐式环境读取」；绿靠的是 EXEMPTIONS 里那条按原文精确匹配的豁免。还原后 sha256 与还原前一致（逐字节）。

### 红 2：判据被改坏 → 自检红（工具自身先被验证）

```bash
cd '/root/better resume'
cp scripts/verify_hermetic.py /tmp/t18-hermetic.bak2
python3 - <<"PY"
from pathlib import Path
p = Path("scripts/verify_hermetic.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
for i, line in enumerate(lines):
    if line.startswith("HOST_PATH = "):        # 变异：H4 判据永不命中
        lines[i] = "HOST_PATH = re.compile(" + chr(34) + "NEVER_MATCHES" + chr(34) + ")" + chr(10)
p.write_text("".join(lines), encoding="utf-8")
PY
python3 scripts/verify_hermetic.py --selftest; echo "EXIT=$?"
cp /tmp/t18-hermetic.bak2 scripts/verify_hermetic.py
sha256sum scripts/verify_hermetic.py /tmp/t18-hermetic.bak2
```

```text
ok   [必红] H1：命中 H1
ok   [必红] H2 键名：命中 H2
ok   [必红] H2 遍历：命中 H2
ok   [必红] H3 PATH：命中 H3
ok   [必红] H3 which 无兜底：命中 H3
ok   [必红] H5 构建期环境：命中 H5
ok   [必绿] 允许形状 5 行：0 命中
EXIT=1
FAIL [必红] H4 home：期望 H4，实得 0 命中（判据被删或改坏）
FAIL [必绿] 豁免：命中 0 处、豁免 1 处（应为 0 与 2）；豁免只认原文精确匹配
FAIL [必红] 改一个字符后豁免仍生效：命中 0 处
自检失败：3 个用例不符预期
e6477f910d9b91d9fd8d8786514941f8704883f39ba9c7675ad24a953aaf617a  scripts/verify_hermetic.py
e6477f910d9b91d9fd8d8786514941f8704883f39ba9c7675ad24a953aaf617a  /tmp/t18-hermetic.bak2
```

### 绿：自检 10/10、真测试树 0 命中

```bash
python3 scripts/verify_hermetic.py --selftest; echo "SELFTEST_EXIT=$?"
python3 scripts/verify_hermetic.py; echo "SCAN_EXIT=$?"
```

```text
ok   [必红] H1：命中 H1
ok   [必红] H2 键名：命中 H2
ok   [必红] H2 遍历：命中 H2
ok   [必红] H3 PATH：命中 H3
ok   [必红] H3 which 无兜底：命中 H3
ok   [必红] H4 home：命中 H4
ok   [必红] H5 构建期环境：命中 H5
ok   [必绿] 允许形状 5 行：0 命中
ok   [必绿] 豁免清单 2 条按原文精确命中并放过
ok   [必红] 豁免按原文匹配：改一个字符即失效（1 命中）
自检通过：10/10 个用例符合预期
SELFTEST_EXIT=0
扫描 140 个测试文件，命中 0 处；豁免 2 处（脚本内清单）。
SCAN_EXIT=0
```

## 验收命令与原始输出

### 1 hermetic 检查（建议 11 的环境半边，P12）

scripts/verify_hermetic.py 的判据是脚本顶部那一段（唯一真源）：H1 读一个具体环境变量（键名不是 BR_ 旋钮）、
H2 读 ambient 代理变量、H3 PATH 走进用例（shutil.which 无 or 兜底 = 静默 skip）、H4 本机绝对路径 / home、
H5 前端测试读 process.env / import.meta.env。扫描面 = apps/api/tests/**/*.py 与 apps/web/src/**/*.{test,spec}.{ts,tsx}。
已知坏样本必红的演示见上面「红 1」「红 2」与绿跑里的 10/10；豁免只有 2 条，都写了理由（脚本内 EXEMPTIONS）。

边界（脚本头部写清，不假装覆盖）：dict(os.environ) / 枚举键名不判（测试替身与环境清理的必要动作）、
相对路径是否指向 gitignored 目录静态判不出读写故不判、真实 sleep / 时钟属建议 11 的时间半边（T16）。

写入路径证据（只写了本票点名的东西）：

```bash
git status --porcelain -- scripts skills docs/tickets/p15-agent-friendly-architecture
```

```text
 M scripts/compose_smoke.sh                     # T21 落地，非本票
 M scripts/fault_injection_drill.sh             # T21 落地，非本票
 M scripts/kill_instance_drill.sh               # T21 落地，非本票
 M scripts/verify.sh                            # 本票：只加 3 行接线（见下）
 M skills/api-index/generated-api-index.md      # 非本票（生成物，索引由脚本刷）
 M skills/modules/llm_gateway/SKILL.md          # 本票：P15-6
?? docs/tickets/p15-agent-friendly-architecture/  # 本票：T18-EVIDENCE.md（阶段目录整体 untracked）
?? scripts/verify_hermetic.py                   # 本票：hermetic 门禁
?? skills/verify-delivery/                       # 本票：交付验证技能（SKILL.md + check_copy.py）
```

属于本票的 verify.sh 三行（git diff 里其余接线是先前 p15 票加的）：

```diff
+  add all "python3 scripts/verify_hermetic.py --selftest"
+  add all "python3 scripts/verify_hermetic.py"
+  add all "python3 skills/verify-delivery/check_copy.py --selftest"
```

### 2 交付验证技能落地（五节，每节可被引用）

```bash
ls -l skills/verify-delivery/
grep -n "^## " skills/verify-delivery/SKILL.md
```

```text
total 20
-rw------- 1 root root  4684 Oct 17 14:27 SKILL.md
-rw------- 1 root root 10576 Oct 17 14:24 check_copy.py
12:## 1 文案判据（F08）
31:## 2 AI 味词表（F08）
42:## 3 中文（F10）
48:## 4 图 · HTML 出口（F09）
56:## 5 改动说明格式（F16）
74:## 自证（先红后绿）
```

五节各自的可操作检查：§1 四个问句 + C1/C4/C5 命令；§2 指向 helper 的 FLAVOR_WORDS（不抄第二份）+ 加词要跑 --selftest；
§3 只写判据 C1 与白名单、语言规则指针回 AGENTS.md §开发规范；§4 给出单文件 HTML 的出口形状与交付前三问 + 样例指针；
§5 四栏模板 + --kind changelog 判 G1/G2。每节都能被别的文档按「文件 + 节标题」引用。

### 3 bash scripts/verify.sh --layer scripts

接线在 --list 里可见（三条本票命令）：

```bash
bash scripts/verify.sh --list | sed -n "/^scripts:/,/^all:/p"
```

```text
scripts:
  all: bash scripts/verify_secrets.sh --selftest
  all: bash scripts/verify_secrets.sh
  all: bash scripts/verify_docs_hygiene.sh --selftest
  all: bash scripts/verify_docs_hygiene.sh
  all: bash scripts/verify_citations.sh --selftest
  all: find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
  all: python3 scripts/verify_hermetic.py --selftest
  all: python3 scripts/verify_hermetic.py
  all: python3 skills/verify-delivery/check_copy.py --selftest
  all: bash scripts/ticket_frontier.sh --selftest
  all: bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
  api: cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
  all: for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo 'shell syntax ok'
  all: uv run --project apps/api python scripts/check_scripts.py
  all: uv run --project apps/api python scripts/verify_audit_evidence.py --structural
       (byte-level citation checking stays the manual --strict close-out step, never a layer -- D22)
all:
```

全层跑（原始日志 var/evidence/20261017T063128Z-scripts/）：**退出 1**，红在 step 12（既有审计逐字级漂移，非本票写入面）：

```text
[7/15] python3 scripts/verify_hermetic.py --selftest
自检通过：10/10 个用例符合预期
[8/15] python3 scripts/verify_hermetic.py
扫描 140 个测试文件，命中 0 处；豁免 2 处（脚本内清单）。
[9/15] python3 skills/verify-delivery/check_copy.py --selftest
自检通过：6/6 个用例符合预期
...
[12/15] cd apps/api && uv run pytest tests/test_fault_probe.py ... tests/test_verify_script.py tests/test_web_style_guards.py
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
1 failed, 100 passed, 2 warnings in 7.22s
FAIL: cd apps/api && uv run pytest ... (log: var/evidence/20261017T063128Z-scripts/12.log)
```

归因（同一份判定代码，比 HEAD 树与工作区）：

```bash
set -euo pipefail
work="$(mktemp -d)"
cd '/root/better resume'
git archive HEAD | tar -x -C "$work"
cd "$work" && "/root/better resume/apps/api/.venv/bin/python" scripts/verify_audit_evidence.py --strict; echo "HEAD_EXIT=$?"
cd '/root/better resume' && python3 scripts/verify_audit_evidence.py --strict; echo "WORKTREE_EXIT=$?"
rm -rf "$work"
```

```text
# HEAD 树（无未提交改动）
verifiable: 122  partial: 0  unverifiable: 0
HEAD_EXIT=0
# 工作区（带在飞未提交改动）
PART  [interview_engine] IE-10: 追问预算 max_follow_up=2 在五处各写一遍，派生路径固定写 2 而不是继承既有预算
        apps/api/src/better_resume/interview_engine/models.py:135-135: 2/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/flow_store.py:37-37: 3/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/question_service.py:277-283: 2/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/restore_service.py:153-156: 0/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/orm.py:180-181: 2/14 evidence lines in window
        apps/api/src/better_resume/http/interview.py:76-76: 2/14 evidence lines in window
verifiable: 121  partial: 1  unverifiable: 0
WORKTREE_EXIT=1
```

本票没有碰 apps/api/** 与 docs/audit/**（git status 见 §1），这条红是在飞的 apps/api 改动造成的引证漂移，按票归 T22 收口重锚。
层里其余各步逐条复跑（step 12 之外）：

```text
[13/15] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"   -> shell syntax ok
[14/15] uv run --project apps/api python scripts/check_scripts.py
        script syntax ok (25 python scripts, SyntaxWarning treated as an error)  -> EXIT=0
[15/15] uv run --project apps/api python scripts/verify_audit_evidence.py --structural
        structure ok: 10 units / 122 issues / 340 citations  -> EXIT=0
```

### 4 技能自证：不合口径的样例文本被逐条点出问题

```bash
work="$(mktemp -d)"
cat > "$work/bad-copy.md" <<"EOF"
- 赋能业务闭环，打造一站式面试平台
- 优化系统性能（响应更快）
- 重构 interview_engine 与 QuestionService 的读写路径，修正 restore 写库
EOF
python3 skills/verify-delivery/check_copy.py "$work/bad-copy.md"; echo "EXIT=$?"
```

```text
HIT [C2] /tmp/tmp.vVKyEP4EPa/bad-copy.md:1 AI 味词「赋能」
    原文：- 赋能业务闭环，打造一站式面试平台
HIT [C2] /tmp/tmp.vVKyEP4EPa/bad-copy.md:1 AI 味词「一站式」
    原文：- 赋能业务闭环，打造一站式面试平台
HIT [C2] /tmp/tmp.vVKyEP4EPa/bad-copy.md:1 AI 味词「闭环」
    原文：- 赋能业务闭环，打造一站式面试平台
HIT [C2] /tmp/tmp.vVKyEP4EPa/bad-copy.md:1 AI 味词「打造」
    原文：- 赋能业务闭环，打造一站式面试平台
HIT [C5] /tmp/tmp.vVKyEP4EPa/bad-copy.md:1 没写清用什么：缺动作动词
    原文：- 赋能业务闭环，打造一站式面试平台
HIT [C3] /tmp/tmp.vVKyEP4EPa/bad-copy.md:2 括号注释：把解释写成第二句
    原文：- 优化系统性能（响应更快）
HIT [C4] /tmp/tmp.vVKyEP4EPa/bad-copy.md:2 量化词没有数字：没有数据就不写量化
    原文：- 优化系统性能（响应更快）
HIT [C5] /tmp/tmp.vVKyEP4EPa/bad-copy.md:2 没写清用什么：缺动作动词
    原文：- 优化系统性能（响应更快）
HIT [C1] /tmp/tmp.vVKyEP4EPa/bad-copy.md:3 西文成句 / 术语成串：interview_engine QuestionService restore
    原文：- 重构 interview_engine 与 QuestionService 的读写路径，修正 restore 写库
EXIT=1
```

合规样本必绿，以及 §5 的改动说明判据（缺栏 + 缺引证）：

```text
$ python3 skills/verify-delivery/check_copy.py good-copy.md
check_copy: 0 命中（kind=cv，/tmp/tmp.vVKyEP4EPa/good-copy.md）        EXIT=0
$ python3 skills/verify-delivery/check_copy.py bad-changelog.md --kind changelog
HIT [G1] /tmp/tmp.k0Q7d8PWlR/bad-changelog.md 改动说明缺栏：影响面、未验证
HIT [G2] /tmp/tmp.k0Q7d8PWlR/bad-changelog.md:1 改动栏没有 文件:行号 引证
EXIT=1
$ python3 skills/verify-delivery/check_copy.py --selftest
自检通过：6/6 个用例符合预期                                    EXIT=0
```

### 5 P15-6：llm_gateway SKILL.md 与实现同步

```bash
git diff -- skills/modules/llm_gateway/SKILL.md
```

```diff
-`SceneResolver`、`SceneBindingStore`、`to_xingyun_payload`、`to_dashscope_app_payload`、
-`XingyunGatewayFactory`、`DashScopeAppFactory`。
+`SceneResolver`、`SceneBindingStore`、`ConfigStatus`、`GatewayFactory`、
+`to_xingyun_payload`、`to_dashscope_app_payload`、`XingyunGatewayFactory`、`DashScopeAppFactory`。
...
-场景绑定的 is_configured 是 **async**（M5 follow-up）：调用处忘了 await 会永远判真。
+场景工厂的配置判断只有 async config_status(binding) -> ConfigStatus 一个签名，一次取回「能不能跑 + 缺哪个变量」的快照；判定读 status.configured（值对象带 __bool__，if not status 读的是同一个值），缺的变量在 status.missing 里。缺这个方法的工厂在 resolve 时以 AttributeError: ... config_status 响亮失败，没有兼容回退。registry 的 ModelRegistry.is_configured 是另一个钩子（同步查 env 里有没有 key），不是场景工厂那一个。
```

新文字与实现对齐（apps/api/src/better_resume/llm_gateway/resolver.py:44-58 的 ConfigStatus、:76 的 async def config_status、
:206-216 的 status = await factory.config_status(binding) / if not status.configured）。

## 收口指针清单（红线：本票不改 AGENTS.md / CODING_STANDARDS 正文，只报位置）

| 位置 | 现状 | 收口动作（后续） |
| --- | --- | --- |
| AGENTS.md §开发规范「语言与沟通」 | 写「全部使用简体中文」 | 加一行指针：判定与白名单见 skills/verify-delivery/SKILL.md §3 |
| AGENTS.md §开发规范「证据诚实」 | 写证据要真、未验证就写未验证 | 加指针到 skills/verify-delivery/SKILL.md §5（改动说明四栏） |
| CODING_STANDARDS.md §4「新规则该放哪」表 | 只有四类落点 | 加一行「交付文案的写作判据与词表」→ skills/verify-delivery/SKILL.md |
| docs/agents/subagents.md §8.2 五栏交接包 | 有五段回报 | 指针到 §5 的改动说明四栏（回报里除「实现决定交代」之外再要四栏） |
| skills/README.md（给 agent 怎么用） | 只有 repo-map / modules / api-index 三条入口 | 加一行「交付前写文案/改动说明 → skills/verify-delivery/SKILL.md」 |

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| hermetic 门禁写成 Python（scripts/verify_hermetic.py）而不是 bash | 判据要按「键名是不是 BR_ 旋钮」分流，bash + awk 得靠字符串切割与引号转义，可读性与可测性都差；仓库已有 Python 门禁（check_web_style_guards.py、verify_audit_evidence.py），scripts/ 的语法已由层里的 check_scripts.py 与 --selftest 兜住 | 没有把判据塞进 pytest（那要写 apps/api/tests/，不在本票写入路径） |
| 判据收窄到「把某个隐式值读出来当输入」的四种形态；dict(os.environ) / 枚举键名、相对路径是否指向 gitignored 目录、真实 sleep 都不判，并把边界写进脚本头部 | 前两种是测试替身与环境清理的必要动作（判了就是误伤，会把人逼去写绕法）；第三种要人判读写语义，静态判不出 | 没有改 apps/api/tests/ 去消掉现有两处合理形态——它们进 EXEMPTIONS（按原文精确匹配 + 写理由），改了就越界 |
| 豁免只给 2 条，且按「相对路径 + 该行原文」精确匹配 | 与 verify_docs_hygiene.sh 的既有口径一致：原文一改即失效、门禁转红，逼人重新判断而不是继承旧豁免 | 没做整文件/整目录豁免，也没放宽判据去换绿 |
| 判据只认双引号键名 | ruff format 已把本仓库统一成双引号；单引号形态要另行处理会引入第二套正则 | 没写单引号兜底（边界写在脚本头部） |
| helper（check_copy.py）放进技能目录而不是 scripts/ | 写路径把 scripts/ 限定成 hermetic 脚本与接线行；create-verification-skill 的方法要求技能自带的脚本可执行、调用写在技能正文里 | 没有把 AI 味词表复制进 SKILL.md（唯一真源在 helper，防两份漂移） |
| 词表/判据表全部放在 helper 里，SKILL.md 只写怎么用；C1（西文成句）只判 --kind cv | 改动说明里的路径与命令是合法的西文，一起判会误伤（实测合规改动说明被 C1 命中 2 行后改成只判 cv，--selftest 的「合规改动说明 0 命中」钉住） | 没有为文案单开一套 --kind report 之类的额外形态，也没有把语言规则原文抄进技能 |
| SKILL.md 加了 YAML frontmatter（name/description） | create-verification-skill 要求 frontmatter 才会注册成技能；仓库现有 skills/*/SKILL.md 都没有 frontmatter，本件按方法产出 | 没有去给其它既有技能补 frontmatter（越界） |
| 层里加了一行 python3 skills/verify-delivery/check_copy.py --selftest | 技能 helper 不在 check_scripts.py 的扫描面里；进层后它至少被真跑一次（语法 + 判据自证都有人管），对应 README 建议 7「每个验证脚本自带已知坏输入必红」 | 没有把 helper 挪进 scripts/，也没有让层去扫描某个固定文案文件（仓库里没有这种被检对象） |

## 未验证项（诚实清单）

1. **bash scripts/verify.sh --layer scripts 全层退出 1**：红在 step 12 的 test_every_audit_citation_is_corroborated_by_its_evidence（审计逐字级 --strict 的 IE-10 partial）。归因已证：同一份判定代码在 HEAD 树 122/0/0 绿、在工作区 121/1/0 红，而本票没碰 apps/api/** 与 docs/audit/**；这条按票属 T22 收口重锚。本票写入的三条层命令（step 7/8/9）与 13/14/15 全绿，step 12 里其余 100 条用例通过。
2. 全量 pytest 在自建隔离库 br_t18_verify 上串行复跑：{'tests': 1017, 'failures': 1, 'errors': 0, 'skipped': 0}（跑完已 drop）；唯一失败与第 1 条同源（审计逐字级）。工作区带其它票的在飞改动，这个读数不代表干净基线。
3. 未做真机 / 浏览器手测：本票只动 scripts/ 与 skills/ 文档，没有可跑的产品面；compose_smoke.sh / 演练脚本未复跑。
4. 技能 §4「图 · HTML 出口」只给了判据、交付前三问与样例指针（docs/audit/MODULE-AUDIT.html），本次没有生成新的 HTML 交付物（没有被要求的交付物可产出）。
5. 门禁的覆盖是刻意收窄的：dict(os.environ)、相对路径指向 gitignored 目录、真实 sleep/时钟这三类不在判据内（边界见脚本头部）；它们要么靠 fixture 与 tmp_path 的人读纪律，要么归 T16 的注入时钟原语。
6. 豁免清单里两条的语义我按当前用例读过（代理清空防护、uv PATH 兜底），但没有逐条向用例作者确认；若某条其实已失效，门禁会因它恒被豁免而看不见。
