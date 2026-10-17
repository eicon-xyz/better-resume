# T26 证据（规则文件改指针：技能/脚本为唯一真源）

票：`docs/tickets/p15-agent-friendly-architecture/T26-rule-pointers.md`；唯一写入路径：`AGENTS.md`、`CODING_STANDARDS.md`（只加指针行）+ 本证据文件。

## 意图复述

1. 交付文案/语言/AI 味/图·HTML 出口/改动说明格式的真源是技能 `skills/verify-delivery/SKILL.md`，测试 hermetic、凭据、历史叙事、引证四条规则的真源是 `scripts/verify_hermetic.py`、`verify_secrets.sh`、`verify_docs_hygiene.sh`、`verify_citations.sh`；`AGENTS.md` 与 `CODING_STANDARDS.md` 不再自成第二份判据。
2. 改法只加指针行：AGENTS.md 在每条被门禁判定的规则旁加一行「判据见 X」，CODING_STANDARDS.md 在 §2 与 §4 各加一行指向技能；规则原文一行不改、不删、不重排、不润色。
3. 验收：`git diff --numstat` 两文件全为新增行且逐行是指针；`bash scripts/verify_docs_hygiene.sh` 与 `bash scripts/verify_citations.sh AGENTS.md CODING_STANDARDS.md` 退出 0；原始输出贴在本文件。

## 红（改动前）

RED-A 两文件对真源零引用（技能/脚本是判定面，规则文件里没有入口）：

~~~bash
cd '/root/better resume'
grep -c 'verify-delivery' AGENTS.md CODING_STANDARDS.md
grep -c 'verify_hermetic.py\|verify_secrets.sh\|verify_docs_hygiene.sh\|verify_citations.sh' AGENTS.md CODING_STANDARDS.md
~~~

~~~text
AGENTS.md:0
CODING_STANDARDS.md:0
AGENTS.md:0
CODING_STANDARDS.md:0
~~~

RED-B 同一条规则正文在两处各存一份（AGENTS.md 行 ↔ 真源行）：

~~~bash
grep -n '测试必须 hermetic' AGENTS.md;             sed -n '7,12p'  scripts/verify_hermetic.py
grep -n '真机凭据' AGENTS.md;                        sed -n '28,33p' scripts/verify_secrets.sh
grep -n '引证行号要重锚' AGENTS.md;                  sed -n '9,16p'  scripts/verify_citations.sh
grep -n '不记录任何 AI 的修改历史' AGENTS.md;        sed -n '14,27p' scripts/verify_docs_hygiene.sh
grep -n '全部使用简体中文' AGENTS.md;                sed -n '42,46p' skills/verify-delivery/SKILL.md
~~~

~~~text
170:- **只 mock 系统边界**（LLM/时钟/Redis/讯飞/浏览器音频/IPC），不 mock 内部模块；测试必须 hermetic——断言不依赖 shell 里的代理变量/PATH/DB 地址。
判据（命中即红，退出码 1）：
  H1 读一个具体环境变量（os.environ[...] / os.environ.get(...) / os.getenv(...)），键名不是 BR_ 旋钮；
  H2 读 ambient 代理变量（键名含 proxy，或无键名地遍历 os.environ 取 *_proxy）；
  H3 PATH 走进用例：读环境里的 PATH，或 shutil.which(...) 没有 or 兜底（缺工具 -> 静默 skip）；
  H4 本机绝对路径 / home 展开（/root/、/home/<user>/、Path.home()、expanduser()）；
  H5 前端测试读构建期环境（process.env / import.meta.env）。
---
61:- 真机凭据**只进仓库根 gitignored `.env`**；`.env.example` 只写变量名，任何密钥不得出现在代码/测试/票据/日志摘录里。
PATTERNS=(
  # PEM 私钥块的头行。
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  # OpenAI / DashScope / DeepSeek 形密钥（含 sk-ws- 前缀）：要求 sk- 之后至少 21 个 [A-Za-z0-9-] 并以字母数字收尾，
  # 于是打码文本 sk-ws-<已打码> 与 OpenSSH 的 sk-ecdsa-sha2-nistp256（恰好 20 个字符）都不够长。
  'sk-[A-Za-z0-9-]{20,}[A-Za-z0-9]'
---
183:- **审计与验证证据**：设计审计在 `docs/audit/`（`units/*.json` 是数据、`CONTRACT.md` 是口径）；`verify_audit_evidence.py` 分两级——CI 只跑结构级（`--structural`，不因代码漂移变红），逐字级（`--strict`）与 `verify_mutation.sh` 是收口手段（D22）。**改过被引用的文件后，引证行号要重锚**，否则逐字级门槛会红。
# 解析规则：
#   1. 引证 = 白名单扩展名的「<路径>:<行号>」，行号可写区间「<起>-<止>」；
#   2. 路径先在 --root（默认仓库根）下直配；直配不到时按 basename 兜底，全树唯一命中才算
#      成功——零命中判「文件不存在」，多命中判「短名歧义」：任选一个会让门禁替错误背书；
#   3. 行号必须落在 1..该文件行数 内；
#   4. 围栏代码块（行首允许缩进、以 ``` 或 ~~~ 切换状态）内的行整行不判——那里贴的是
#      门禁原始输出与样本，里面的「文件:行号」是引文不是引证；行内 code 不豁免
#      （行内引证是真引证）。
---
9:2. **文档与代码注释只描述当前状态，不记录任何 AI 的修改历史。** 不写「本次改动」「之前是 X、现在改为 Y」
PATTERNS=(
  # 改版前后的对比叙事（「之前是 X，现在改为 Y」）。描述现状不需要这个时间状语；
  # 「之前」单独出现不拦，只拦陈述旧值的「之前是」。
  '之前是'
  # 轮次叙事（手测第几轮通过、第几轮修）。重试/轮询写「重试」「轮询」，不会写成「第…轮」；
  # 「第 N 层 / 第 N 步」等量词不受影响。
  '第[[:space:]]*(N|[0-9]+)[[:space:]]*轮'
  # 弃用史。当前状态直接说「不再使用」或删掉该节；无技术术语需要写「已废弃」。
  '已废弃'
  # 踩坑史，只出现在复盘叙述里，没有技术语义。
  '曾经踩过'
  # 被取代的旧决策留痕。文档只写当前生效的决策，不告诉读者哪条作废。
  '已作废'
)
---
169:- 语言与沟通：全部使用简体中文（注释、文档、对话）；提交信息用英文短句说 WHAT（如 `fix(media): …`）。
## 3 中文（F10）

- 语言约束的真源是 `AGENTS.md` §开发规范（全部使用简体中文）；本节只写**怎么判定**，不复述那条规则。
- 判据 C1：一行里 3 个及以上西文词（不在 helper 的 `ALLOWED_TERMS` 白名单）就是「成句西文」→ 改成中文句子；白名单里的专业名词保留原文。
- 判定命令同 §1；退出码非 0 就是不合口径，它逐条点名 行号 + 判据 + 原文。
~~~

RED-C 引证口径真会判我写的那种指针行（坏指针必红，退出码 1）：

~~~bash
printf '%s\n' '- 判定见 skills/verify-delivery/SKILL.md:9999（§3）' > bad.md
printf '%s\n' '- 判定见 skills/verify-delivery/NOPE.md:1（§3）' > bad2.md
bash scripts/verify_citations.sh bad.md bad2.md; echo "EXIT=$?"
~~~

~~~text
FAIL /tmp/tmp.Mlhhvu218P/bad.md:1 引证「skills/verify-delivery/SKILL.md:9999」：行号 9999 越界（skills/verify-delivery/SKILL.md 共 92 行）
FAIL /tmp/tmp.Mlhhvu218P/bad2.md:1 引证「skills/verify-delivery/NOPE.md:1」：文件不存在（整仓没有 basename 为 NOPE.md 的文件）
引证 2（直配 0，短名兜底 0）解析成功 0 失败 2
EXIT=1
~~~

RED-D docs_hygiene 自检：豁免按 AGENTS.md 原文精确匹配，改一个字符即红（两份正文漂移的可判定形态）：

~~~text
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
EXIT=0
~~~

RED-E 改动前基线（两条验收命令此时都是绿，但引证条数是 0——指针还不存在）：

~~~text
$ bash scripts/verify_docs_hygiene.sh
扫描 530 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
EXIT=0
$ bash scripts/verify_citations.sh AGENTS.md CODING_STANDARDS.md
引证 0（直配 0，短名兜底 0）解析成功 0 失败 0
EXIT=0
~~~

## 绿（改动后）

GREEN-1 与 GREEN-2 是票面验收命令：

~~~text
$ bash scripts/verify_docs_hygiene.sh
扫描 532 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
EXIT=0
$ bash scripts/verify_citations.sh AGENTS.md CODING_STANDARDS.md
引证 6（直配 6，短名兜底 0）解析成功 6 失败 0
EXIT=0
~~~

（被扫文件数随在飞改动增减：改动前那一刻是 530，收工复跑是 532；两条命令的退出码与引证条数不受影响。）

引证条数从 0 变 6：新增的 6 条指针引证全部直配成功（`scripts/verify_secrets.sh:28-41`、`skills/verify-delivery/SKILL.md:42`、`scripts/verify_hermetic.py:7-12`、`skills/verify-delivery/SKILL.md:56`、`scripts/verify_citations.sh:9-16`、`scripts/verify_docs_hygiene.sh:14-41`）。

GREEN-3 票面「验收口径 3」把 `verify_docs_hygiene.sh` 写成 `python3` 调用，实际按 bash 跑；两种写法的原始输出：

~~~text
$ python3 scripts/verify_docs_hygiene.sh
  File "/root/better resume/scripts/verify_docs_hygiene.sh", line 5
    set -euo pipefail
             ^^^^^^^^
SyntaxError: invalid syntax
EXIT=1
$ bash scripts/verify_docs_hygiene.sh --selftest
自检通过：11/11 个用例符合预期
EXIT=0
~~~

GREEN-4 `git diff --numstat -- AGENTS.md CODING_STANDARDS.md`：

~~~text
9	3	AGENTS.md
2	0	CODING_STANDARDS.md
~~~

AGENTS.md 的 9 增 3 删 = 我加的 6 行指针 +（用户未提交的 in-flight 改动 3 增 3 删，红线要求零触碰）。机械证明：把我加的 6 行剔除后与 HEAD 逐行比，差异只剩 in-flight 那三处：

~~~bash
grep -v -e '^  - 判定见 ' -e '^  - 改动说明的四栏' -e '^  - 引证能否解析' -e '^- 改了文档或注释的文字：' AGENTS.md > rec.md
git show HEAD:AGENTS.md > head.md
diff -u head.md rec.md
~~~

~~~text
--- head.md
+++ rec.md
@@ -23,7 +23,7 @@
   - `apps/web`：React 19 + Vite SPA 前端。
   - `docs/`：决议 / 交接 / 各阶段票据与验收包 / 容量报告。**接手先读 `docs/HANDOFF.md`**。
   - `skills/`：给 AI 的导航——repo-map（"改 X 先看哪"）+ 每个深模块一个 SKILL.md + 生成的 API 索引。
- 决议记录在 `docs/DECISIONS.md`（D01–D25），术语表在 `GLOSSARY.md`。**判定权**：选型与范围以 DECISIONS.md 为准，工程规范以本文为准；`docs/HANDOFF.md` 是**带日期的状态快照**（管「现在什么状态、怎么跑」），里面的数字可能过期，冲突时以实测为准。
+ 决议记录在 `docs/DECISIONS.md`（D01–D26），术语表在 `GLOSSARY.md`。**判定权**：选型与范围以 DECISIONS.md 为准，工程规范以本文为准；`docs/HANDOFF.md` 是**带日期的状态快照**（管「现在什么状态、怎么跑」），里面的数字可能过期，冲突时以实测为准。

## 技术栈

@@ -47,7 +47,7 @@
 - `uv` 在 `~/.local/bin`：新 shell 先 `export PATH="$HOME/.local/bin:$PATH"`。
 - 子智能体等沙箱里 `uv` 默认写工作区外的 `/root/.cache/uv` → 权限拒绝；先 `export UV_CACHE_DIR='/root/better resume/.cache/uv'`。
   症状：`uv run pytest` 报 cache 错，而 `./.venv/bin/python -m pytest` 照跑。
- pytest **必须显式导出测试库地址**，否则依赖 DB 的用例会 skipped（不是失败，实测能一次吞掉 136 例）：
+ pytest **必须显式导出测试库地址**，否则依赖 DB 的用例会 skipped，`test_interview_api.py` 的 `interview_type` 用例还会直接 FAILED（缺 DB 不可达守卫，直连默认 :5432 被拒）——静默面同时含 skip 与 fail；条数看 `--junitxml` 读数，别抄固定值：

   ```bash
   cd apps/api
   export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
   export BR_REDIS_URL='redis://127.0.0.1:6379/0'
   ```

@@ -76,7 +76,7 @@ bash scripts/verify.sh --layer real --dry-run # 真机清单 + 预算（不花
 # 变异证明：断言「这段测试真的钉住了这段实现」——基线绿 → 变异红 → 恢复绿，脚本真看退出码
 bash scripts/verify_mutation.sh --test "..." --file <path> --find "<锚点>" --replace "<变异>"

-# 后端全量测试（例数看 --junitxml 读数；不导出 BR_* 会静默 skip 136 例）
+# 后端全量测试（例数看 --junitxml 读数；不导出 BR_* 会静默 skip 一批依赖 DB 的用例，个别还 FAILED）
 cd apps/api && uv run pytest -q --junitxml=/tmp/x.xml
~~~

（`diff -u` 退出 1 = 有差异，属预期；上面删掉的 3 行全部是用户 in-flight 行。）

GREEN-5 我加的 8 行指针（逐行说明，全部来自 GREEN-4 的 `+` 行）：

~~~text
AGENTS.md:62    - 判定见 `bash scripts/verify_secrets.sh`（命中即红，只打印 `文件:行号`；凭据形状表是 `scripts/verify_secrets.sh:28-41`，判据勿在此复制）。
AGENTS.md:171     - 判定见 `skills/verify-delivery/SKILL.md:42`（§3 中文：C1 成句西文判据与白名单）——判据正文只在该技能，勿在此复制。
AGENTS.md:173     - 判定见 `python3 scripts/verify_hermetic.py`（判据 H1–H5 与豁免清单是 `scripts/verify_hermetic.py:7-12` 与脚本内 `EXEMPTIONS`）——判据表只在该脚本，勿在此复制。
AGENTS.md:181     - 改动说明的四栏与命令引证形状见 `skills/verify-delivery/SKILL.md:56`（§5；字段与引证判定由 helper 的 `--kind changelog` 跑）——判据只在技能与 helper，勿在此复制。
AGENTS.md:188     - 引证能否解析的判定见 `bash scripts/verify_citations.sh`（直配/短名兜底、行号越界即红的规则在 `scripts/verify_citations.sh:9-16`）——解析规则只在该脚本，勿在此复制。
AGENTS.md:197   - 改了文档或注释的文字：`bash scripts/verify_docs_hygiene.sh`（禁词集与按原文精确匹配的豁免清单在 `scripts/verify_docs_hygiene.sh:14-41`）——判据勿在此复制。
CODING_STANDARDS.md:23  - **`skills/verify-delivery/SKILL.md`**：交付文案判据、中文判定、AI 味词表、图·HTML 出口、改动说明四栏——判据表与词表在技能自带的 helper，勿复制进本文件。
CODING_STANDARDS.md:48  | 交付文案的写作判据与 AI 味词表（F08/F10/F16） | `skills/verify-delivery/SKILL.md`（判据表唯一真源在它自带的 `check_copy.py`，勿复制） |
~~~

逐行归类：6 行是「规则 → 门禁/技能」的指针（凭据→secrets、中文→技能 §3、hermetic→脚本 H1–H5、证据诚实→技能 §5、引证重锚→citations、历史叙事→docs_hygiene），2 行是 CODING_STANDARDS 的标准入口（§2）与落点表（§4）指针。规则正文一行未改，章节顺序未动。

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 指针行贴在被判定的规则正下方（缩进两格），不新开章节、不汇成一张总表 | 读者在规则处就拿到判定入口；缩进行不改任何既有行的层级与顺序，diff 里只有新增 | 没有把四条门禁 + 技能汇成一张新表（那会多出一份需要维护的清单，正是本票要消灭的形态） |
| 硬规则 2 对应的 docs_hygiene 指针放在 §贡献指南（提交前检查清单），不放硬规则块内 | 红线要求硬规则语义零改动；§贡献指南本来就列门禁命令（compose_smoke、kill_instance_drill），形态一致 | 没有改硬规则三条、三条闸门的任何一个字；没有把指针塞进硬规则 2 的子项 |
| 只走「注明判据见 X」这一支，不删 AGENTS.md 里的规则原文 | 规则原文是给人读的规则，脚本/技能是判定面；删原文既改语义，又会砸掉 docs_hygiene 里按原文精确匹配的豁免（删字即红） | 没有执行「复制的规则正文清零」的删除分支；没有改门禁的禁词集或豁免清单 |
| 6 条指针都带 `文件:行号` 引证，而不是只写节名 | 票面要求「指针必须指向存在的文件/节（过引证门禁）」；`verify_citations.sh` 只认 `路径:行号`，带行号后该命令从「引证 0」变成「引证 6 全部直配成功」，指针存在性由门禁真判 | 没有为行号漂移加缓解机制（漂移即红，按 §开发规范的重锚纪律办） |
| CODING_STANDARDS 加两处（§2 标准入口 + §4 落点表），不只加 §4 一行 | §4 是「新规则该放哪」，§2 才是评审方找「仓库标准在哪」的入口；只加 §4 评审仍找不到技能 | 没有在 §1「工具已经拦下的」表里补四条门禁行（本次票没要求，且那是层接线的事） |
| 票面验收口径 3 的 `python3 scripts/verify_docs_hygiene.sh` 按 `bash` 跑 | 该文件是 bash 脚本，用 python3 跑它是 SyntaxError（原始输出见 GREEN-3）；门禁自身用法注释写的是 `bash` | 没有改脚本解释器或门禁代码去迎合票面写法 |
| T18 收口指针清单里的第 4、5 处（`docs/agents/subagents.md` §8.2、`skills/README.md`）不在本票唯一写入路径内 | 红线把写入路径限定为 `AGENTS.md` 与 `CODING_STANDARDS.md`；越界写第三个文件即违规 | 没有动那两个文件（另开票或由主代理派活处理） |

## 未验证项（诚实清单）

1. 未跑 `bash scripts/verify.sh --layer scripts` 全层：本票两条门禁确实在层内（`scripts/verify.sh:99-103`），但该层另有与本票无关的存量红（审计逐字级，见 T18-EVIDENCE 未验证项第 1 条与 T22）。
2. 未跑后端 pytest / 前端 vitest：本票只改两个 markdown 与一个证据 markdown，没有代码面。
3. 未做真机 / 浏览器手测：没有可跑的产品面。
4. 门禁只判「指针指向的文件存在、行号不越界」，判不出「这个行号是不是我要指的那一节」；6 条指针的节名与行号（SKILL §3/§5 标题行、四条门禁的判据/规则行）由我人工核对。
5. 本次未生成 HTML 交付物（本票没有要求结论可视化）。
