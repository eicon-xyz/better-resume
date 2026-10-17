# T11 证据：修掉 p11/p12 的失效引证

## 意图复述

- 我理解这票解决什么：p11/p12 的票据与验收包里，有 4 条引证过不了 `scripts/verify_citations.sh`——3 条是 `orm.py` 短名歧义（全树 3 个同名文件），1 条是 `settings_config.py` 在整仓不存在；票要把这 4 条改到能复核的真实位置。
- 我怎么做，到文件粒度：`docs/tickets/p11-resume-driven-questions/README.md` 的第 23、25、28 行三处引证改成唯一全路径并按当前代码重锚行号；`docs/tickets/p12-intent-alignment/ACCEPTANCE.md` 第 69 行那处引证改指真实存在的 settings 模块。只动这 4 行。
- 我不做什么：不改章节结构与编号、不改引证以外的任何文字；不动 p15 目录（除本证据文件外）与其他文档；不动工作区里 p14 在飞的未提交改动；不 commit / push / 开 PR。

## 红-绿（先按票演示红）

红用的坏输入 = 修前版本，直接取 `HEAD`（改动前工作区对这两个文件是干净的，`git diff --numstat` 对两目录无输出，所以 `HEAD` 就是票面基线）：

```bash
cd "/root/better resume"
TMP=$(mktemp -d)
git show HEAD:docs/tickets/p11-resume-driven-questions/README.md > "$TMP/README.md"
git show HEAD:docs/tickets/p12-intent-alignment/ACCEPTANCE.md > "$TMP/ACCEPTANCE.md"
bash scripts/verify_citations.sh "$TMP/README.md" "$TMP/ACCEPTANCE.md"; echo "EXIT=$?"
```

原始输出（2026-10-17，TMP=`/tmp/tmp.rjI5RIIBN7`）：

```text
FAIL /tmp/tmp.rjI5RIIBN7/README.md:23 引证「orm.py:72-95」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL /tmp/tmp.rjI5RIIBN7/README.md:25 引证「orm.py:166-168」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL /tmp/tmp.rjI5RIIBN7/README.md:28 引证「orm.py:47-65」：短名 orm.py 歧义，命中 3 个：apps/api/src/better_resume/conversation/orm.py apps/api/src/better_resume/interview_engine/orm.py apps/api/src/better_resume/llm_gateway/orm.py
FAIL /tmp/tmp.rjI5RIIBN7/ACCEPTANCE.md:69 引证「settings_config.py:8」：文件不存在（整仓没有 basename 为 settings_config.py 的文件）
引证 20（直配 3，短名兜底 13）解析成功 16 失败 4
EXIT=1
```

（同一命令在改动前的工作区上跑过一次，输出与上面四行逐字相同，`EXIT=1`。）

## 验收命令与原始输出

### 1. 门禁退出 0、失败 0

```bash
cd '/root/better resume'
bash scripts/verify_citations.sh docs/tickets/p11-resume-driven-questions/*.md docs/tickets/p12-intent-alignment/*.md; echo "EXIT=$?"
```

```text
引证 21（直配 8，短名兜底 13）解析成功 21 失败 0
EXIT=0
```

### 2. `git diff --numstat` 只含这两个目录，改动行数 ≤ 修复条数

```bash
git diff --numstat -- docs/tickets/p11-resume-driven-questions docs/tickets/p12-intent-alignment
```

```text
3	3	docs/tickets/p11-resume-driven-questions/README.md
1	1	docs/tickets/p12-intent-alignment/ACCEPTANCE.md
```

一个文件 3 条、另一个 1 条，合计 **4 条修复 = 4 行改动**（`git diff --stat` 给 `2 files changed, 4 insertions(+), 4 deletions(-)`）。
未限定路径的 `git diff --numstat` 另有 34 个文件、`git status --porcelain` 47 条——全部是工作区里 p14 在飞的未提交改动，本票零触碰。

### 3. 非引证文字零改动

```bash
git diff --word-diff=plain -- docs/tickets/p11-resume-driven-questions/README.md docs/tickets/p12-intent-alignment/ACCEPTANCE.md
```

```text
| 题目**没有类别字段**，唯一类型字段是 `kind` ∈ {main, follow_up} | [-`orm.py:72-95`-]{+`apps/api/src/better_resume/interview_engine/orm.py:100-125`+}；`question_service.py:197` |
| 报告四维只按 主问题 / 追问题 两个桶聚合 | `report_service.py:251-257`；`dimensions` 是 [-JSONB（`orm.py:166-168`）-]{+JSONB（`apps/api/src/better_resume/interview_engine/orm.py:196-198`）+} |
| 解析产物 `ResumeContext` **不落库**（只存 `resume_path`/`sha256`） | [-`orm.py:47-65`-]{+`apps/api/src/better_resume/interview_engine/orm.py:70-71`+}；`storage.py:17-33` |
| **#1** 新设置进了 [-`settings_config.py:8`，但-]{+`apps/api/src/better_resume/settings/config.py:133`，但+} `compose.yaml` 与 `env.example` 都没有对应行 | ... |
```

（上面按行摘录；完整 `--word-diff=plain` 输出里 `[-...-]` / `{+...+}` 只出现在这 4 处的引证 token 上。）

旁证：两个文件行数未变（151 / 257），改动里 `^##` 标题行计数为 0（章节标题与编号零改动）。

### 4. 附带对照（不计入本票验收）

```bash
bash scripts/verify_citations.sh $(find docs/tickets -name "*.md" | LC_ALL=C sort); echo "fulltree exit=$?"
bash scripts/verify_docs_hygiene.sh; echo "hygiene exit=$?"
```

```text
FAIL docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md:194 引证「T5-EVIDENCE.md:155」：短名 T5-EVIDENCE.md 歧义，命中 3 个：docs/history_docs/tickets/m6/T5-EVIDENCE.md docs/tickets/p14-web-redesign/T5-EVIDENCE.md docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md
引证 176（直配 73，短名兜底 102）解析成功 175 失败 1
fulltree exit=1
扫描 496 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
hygiene exit=0
```

全票据树里 p11/p12 已无 FAIL 行（改前第 67-70 行那 4 条就是它们）；剩下 1 条在他票文件（`T5-EVIDENCE.md:194`，p15 目录正被并发写入），不在本票写入路径内。全树报数 176 与 T7 快照的 364 口径不同（文件清单不同），只作对照、不作读数。

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| p11 README 那三条引证除改全路径外，还按当前代码**重锚了行号**（72-95→100-125、166-168→196-198、47-65→70-71） | 只补全路径会让引证落到同名文件里**别的类**上（`interview_engine/orm.py:72-95` 是 session 行的字段），门禁照样绿而引证在撒谎；票面「失效引证改正」与 p11 `PROBLEMS.md` §4「实现移位导致引证失效」都指向重锚。三处新窗口分别覆盖 `InterviewQuestionRow`（`kind` 在 115）、`InterviewReportRow.dimensions` 的 JSONB、session 行的 `resume_path`/`resume_sha256` 两列 | 没改指另外两个同名 `orm.py`（`conversation/` 与 `llm_gateway/` 都不含这几张表） |
| p12 那条改指 `apps/api/src/better_resume/settings/config.py:133`（`class Settings(BaseSettings)`） | 票面口径是「找不到对应文件的引证改为指向真实存在的位置」。`settings_config.py` 是消融材料的合成摘录（材料随临时目录已删），仓库里的对应物就是真实 settings 模块；行号取 133，因为「新设置进了设置文件」的落点就是 Settings 类的字段声明处，而真实文件的第 8 行是空行 | 没改指 `var/rule-audit/ablation-run2.md:12`（那条材料记录仍在）：`var/` 是 gitignored，p12 自己的口径写的是「var/ 不进 git，只引路径等于没有证据」（本文件 §1.1 标题原文），指过去会重新变成坏引证；也没删这条引证 |
| 本票在 p15 目录唯一的写入是 `T11-EVIDENCE.md` 本身 | 票面 §意图复述与实现决定交代 明确要求这两段落在该文件；按 `docs/agents/subagents.md` §8.3，票据自身两段自述不计入「唯一写入路径」 | 没动 p15 目录里的任何其他文件（含 T10 在飞的产物、`pitfalls-report.md`、`recall-report.md`） |
| 只修门禁点名的那 4 条，同表里已过门禁的其他短名引证（`question_service.py:197`、`report_service.py:251-257`、`storage.py:17-33`、`prompts.py:*` 等）一律不动 | 票的范围是「跑命令取失败清单」，绿的不在清单里；顺手重锚会把改动面扩大到他票/他章节的引证 | 没重锚任何未被门禁点名的引证 |
| 出力顺序：先写 `## 意图复述` 落盘，再开始改引证 | 票面要求开工先追加该段 | 没把两段自述写进任何引证文件或 p11/p12 目录 |

## 未验证项

- **p11 README §1.2 是开工前的现状快照，重锚后的引证与那句话的时态对不齐**：第 23 行说的是「题目没有类别字段」，而 `interview_engine/orm.py:116` 现在有 `category`（p11 自己加的）。窗口已指向题目行的声明处，但「这句话描述的旧事实现在无法取证」是残留问题；改措辞会越过票面「非引证文字零改动」，故未改。
- **p12 ACCEPTANCE 第 69 行同理**：该行是消融材料的摘要，引证按票面改指真实 settings 模块后，字面上读起来像在说真仓库「新设置进了 config.py 而 compose 没同步」——那件事只发生在合成材料里（真仓库现在没有 `BR_REPORT__FREEZE_AFTER_SECONDS` 这个变量）。未改措辞，同属「非引证文字零改动」。
- **只核了行号窗口与「被指代的那段声明」对得上，没逐字复核其余过门禁的引证是否也已随实现漂移**——门禁只判存在性与行号范围，语义漂移它判不出来（票的范围也只要前者）。
- **门禁尚未接进 `scripts/verify.sh`**（`grep verify_citations scripts/verify.sh` 无输出），所以这次绿不会自动出现在 CI；接线是 T8 的事，本票未碰。
- **全树读数（176/175/1）只是快照**：p15 目录正被其他票并发写入，且与 T7-EVIDENCE 的 364 条口径不同（文件清单不同），未做口径对齐。
- 未跑 pytest / `verify.sh` 任何层、未跑前端测试与契约三件套：本票只动两个 markdown 文件里的 4 个引证 token，不涉代码与 REST 模型；跑了 `verify_docs_hygiene.sh`（全树 0 命中）作为文档面旁证。
- 未 commit / push / 开 PR；未碰工作区里 p14 在飞的 34 个已改文件与未跟踪文件。


