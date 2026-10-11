# P12 验收包：意图对齐与验收减负

- **状态**：待用户验收（AI 不自行宣布完成；未提交、未推送、未开 PR）
- 提案：`README.md`（§1.4 决策表 Q1–Q5）；票据：`T1`–`T5`（一票一文件）；难题台账：`PROBLEMS.md`
- 执行方：`opencode-go/deepseek-v4.1-flash`（4 个实现轮 + 2 个修复轮 + 1 个单行修复）
- Spec 轴评审：`dashscope/qwen3.8-flash`（异家族同级，3 轮）；Standards 轴 + 意图一致性：规划方

## 1. 交付物对账（按提案 §3）

| 提案项 | 落地位置 | 读数 |
| --- | --- | --- |
| 人工高风险面清单 | `CODING_STANDARDS.md` §5 | 五类齐全（权限与认证 / 状态变化与幂等 / 并发与重试 / 数据一致性与迁移回滚 / 对外契约与降级语义），每格是检查动作不是规定 |
| 评审必答问题 | `CODING_STANDARDS.md` §6 | **8 条**（= 上限），每条含 问题 / 证据形式 / 不适用条件 / 出处；证据形式为三种：命令+原始输出摘录、`文件:行号`、`文件:节名`（决议用 D 号） |
| 票据「意图复述」+「实现决定交代」 | `docs/agents/issue-tracker.md` 新节 | 五块齐全（含验收包两栏与票据尺寸上限） |
| 验收包「自行拍定的决定」+「改动面与高风险面自查」 | 同上 | 聚合表要求**至少含一列票标识**；改动面要求与声明写入路径逐条比对、**越界即红**（票据自身末尾两段自述不计入） |
| 跨模型交接格式 + 评审双轴分派 | `docs/agents/subagents.md` §8 | 六个子节；五栏（缺一不可）；「不接受的自由度」定义 + 6 例；Spec 轴异家族 / Standards 轴规划方 |
| 规则删除候选清单 | `var/rule-audit/candidates.md`（73 行，gitignored） | 候选 **3 条** / 保留但可自动化 **9 条**；摘要见本包 §1.1 |
| 机制消融记录 | `var/rule-audit/ablation.md`（gitignored，摘要见 §1.2） | 对象按 Q7 改为 §6 机制本身；**总调用 5 次**（4 次 A/B + 1 次隔离校准） |
| 验收包 | 本文件 | — |

### 1.1 `var/rule-audit/candidates.md` 摘要（var/ 不进 git，只引路径等于没有证据，故抄录于此）

判定口径：能被 `verify.sh` 例行层（CI 实际跑的 unit / contract / coverage / scripts，即 `--layer all`）或 CI 发现 → 删除候选；只能靠验收包 / 手测 / 发现不了 → 保留。

| # | 删除候选 | 执行方的一行结论 | 规划方复核 |
| --- | --- | --- | --- |
| 1 | `AGENTS.md` §贡献指南 L187（ruff / 全量 pytest） | CI 的 contract 层与 unit 层已跑，删掉后最坏只是提交后 CI 红一轮 | 推理成立，**建议保留**：它还承担 `CODING_STANDARDS.md` §2 指回的「改动类型 → 必跑命令」映射 |
| 2 | `AGENTS.md` §贡献指南 L188（前端 test/lint/tsc + 契约三件套） | 同一批命令 CI 的 unit 与 contract 层已跑，最坏是契约漂移在 CI 才红 | 推理成立，**建议保留**，同上 |
| 3 | `AGENTS.md` §贡献指南 L191（可选启用 git hooks） | hooks 跑的两件事在 scripts 层与 contract 层已跑 | **否决**：它是 `.githooks/pre-commit` 唯一的发现入口，属能力指针不属规则；检验口径套错对象（见 `PROBLEMS.md` §6） |

「保留但可自动化」9 条：`AGENTS.md` L170（只 mock 系统边界）、L172（供应商调用走 `ai_resilience` 链）、L173（错误语义 503+Retry-After）、L174（缓存 TTL / 写路径失效）、L175（WS 转写关闭码与追加语义）、L177（证据诚实）、L178（依赖纪律）、L182（测试的共享状态自己还原）、`CODING_STANDARDS.md` L30（声称验证过的脚本必须真判定）。
**只列不实施**；执行方声明未读 `apps/api/tests/**`，故「是否其实已有会红的检查」未核实（见 §7）。

例外直判保留（未进候选）：三条闸门、硬规则 1/2/3、凭据与密钥相关条款——全部命中，无一被当作候选。

### 1.2 `var/rule-audit/ablation.md` 摘要（T5 机制消融）

**判定：任务失效——主问题未得到回答。** 按 T5 判定表，A 组不犯错即任务失效，**不许硬判「§6 有效」**。

装置：A/B 同款 `opencode-go/deepseek-v4.1-flash`，cwd 在仓库外的隔离目录（每目录只有 `contract.md` + `report.md`），任务文本逐字相同，**唯一变量**是 B 组 prompt 末尾附 §6 八条原文（1718 字符）。埋的违规是「报告把实测 `500` 判为符合预期，而契约要求 `503 + Retry-After` 并点名缺失变量」；另 3 行是真的对的（避免「全否」得分）。

**隔离校准**：workspace instructions 未注入，但受试者报告**仍能用工具读到**仓库里的 `AGENTS.md` / `CODING_STANDARDS.md`——子代理继承文件系统访问权，规划方无收窄手段。**隔离只做到 prompt 级**。补救是两组同样的显式禁读 + 污染检测器（11 个 §6 特征串）。

| 组 | 受试者 | 埋的违规 | 污染检测器 |
| --- | --- | --- | --- |
| A（不给 §6） | a1 | **抓住** | **0 命中** → 试验有效 |
| A（不给 §6） | a2 | **抓住** | **0 命中** → 试验有效 |
| B（给 §6） | b1 | **抓住** | 1 命中（预期） |
| B（给 §6） | b2 | **抓住** | 1 命中（预期） |

三条结论：

1. **主问题未回答**：违规太显眼（契约就在同目录、`500` vs `503` 是明文冲突），A 组 2/2 抓住 → 测不出 §6 的增量。这是**任务失效**，既不是「§6 无效」也不是「§6 有效」。
2. **次生观察（n=2，不作为结论）**：B 组 **2/2** 都施加了「证据形式」要求（原始输出摘录 / `文件:行号`）并把三行干扰项降级为「证据偏弱」，A 组只有 1/2 提了较弱版本。差异指向 §6 **导语里的证据形式规定**，而不是八条问题清单本身。
3. **§6 的设计缺陷（本票最有价值的产出）**：b1 **拒绝回答那 8 条**，理由是证据要求指向可读范围之外的文件，且它不肯用「不适用/已确认」凑答案。§6 只定义了「本次改动没有 X」这一种不适用，**没有定义「我读不到所需证据」**——在按「唯一写入路径 + 点名文件」收窄范围的派活里，评审方要么伪造、要么拒答。见 `PROBLEMS.md` §9。

口径：每组 **n=2**、只测 §6 第 1 条对应的违规形态、任务形态是「审阅报告」而非真实改代码。**这不是统计结论，是一次可行性判定。**

## 2. 改动面与高风险面自查（按本阶段新建的模板自应用）

### 2.1 `git diff --stat` 原始输出

```
 CODING_STANDARDS.md          | 57 ++++++++++++++++++++++++++++++++++++++++++++
 docs/agents/issue-tracker.md | 50 ++++++++++++++++++++++++++++++++++++++
 docs/agents/subagents.md     | 48 +++++++++++++++++++++++++++++++++++++
 3 files changed, 155 insertions(+)
```

`git diff --numstat` → `57 0` / `50 0` / `48 0`：**三个文件全部纯追加，删除行 0**。

### 2.2 与声明的唯一写入路径逐条比对

| 票 | 声明的写入路径 | 实际改动 | 判定 |
| --- | --- | --- | --- |
| T1 | `CODING_STANDARDS.md` | `CODING_STANDARDS.md` +57/−0 | 一致 |
| T2 | `docs/agents/issue-tracker.md` | `docs/agents/issue-tracker.md` +50/−0 | 一致 |
| T3 | `docs/agents/subagents.md` | `docs/agents/subagents.md` +48/−0 | 一致 |
| T4 | `var/rule-audit/candidates.md` | 该文件（gitignored）；规则文件零改动 | 一致 |
| T5 | — | 未执行 | — |

票据自身末尾的「意图复述」「实现决定交代」两段按 `docs/agents/subagents.md` §8.3 不计入写入路径。
**无越界。** `git status --porcelain` 全量输出：

```
 M CODING_STANDARDS.md
 M docs/agents/issue-tracker.md
 M docs/agents/subagents.md
?? docs/tickets/p12-intent-alignment/
```

`AGENTS.md`、`docs/tickets/p11-resume-driven-questions/`、`docs/history_docs/**` 全程**零改动**（`git status --porcelain` 对它们无输出）。

### 2.3 按 `CODING_STANDARDS.md` §5 五类逐类勾

| 类 | 碰了 / 没碰 | 证据 |
| --- | --- | --- |
| 权限与认证 | **没碰** | `git diff --numstat` 只有 3 个 markdown 文件，`identity/`、`http/` 零改动 |
| 状态变化与幂等 | **没碰** | 同上；`interview_engine/`、迁移目录零改动 |
| 并发与重试 | **没碰** | 同上；`ai_resilience/` 零改动 |
| 数据一致性与迁移回滚 | **没碰** | 无新迁移；`alembic check` 未被触发（无模型改动） |
| 对外契约与降级语义 | **没碰** | `openapi.json`、`schema.d.ts` 零改动，契约三件套无需跑 |

本阶段是纯文档阶段，五类全部「没碰」——这一栏的价值正是让你不用再去看那五片代码。

## 3. 自行拍定的决定（跨票聚合）

与「与提案的偏差」（§5）**并列，不合并**。偏差 = 偏离了 spec；自行拍定 = spec 没说、执行方补了。

| 票 | spec 未覆盖、自行拍定的决定 | 为什么这么拍 | 明确没做的 |
| --- | --- | --- | --- |
| T1 | §5 用 markdown 表格承载「类 / 看什么 / 出处」三栏 | 票据只写「一类一行、三栏」，未指定形态 | 没改成编号清单，没增删类目 |
| T1 | §6 每条内部用两空格缩进普通行，不用子列表 | 票据给的样例本身就是这个格式 | 没为凑格式省掉证据栏或「不适用」出口 |
| T1 | §5、§6 各加一句导语 | 「检查动作不是规定」「证据形式」「不适用是合法回答」这些口径在票据里没有落点 | 没借导语引入新规则、新工具或新流程名词 |
| T1 | 出处栏逐字保留票据给出的出处 | 改写出处等于替换「指回哪条既有规则」 | 没替换、合并或新增任何一条种子的出处 |
| T2 | 适用范围写在节首而不是节尾 | 票据只说「必须写进新节」，未定位置 | 没在每个子块重复一遍 |
| T2 | 放弃「在『目录约定』句末加指针」这个可选项 | 加指针会产生删除行，与「diff 只有追加行」的验收口径互斥 | 没为可发现性改任何既有句子 |
| T2 | 高风险面自查只指回 §5 节名，不复制五类原文 | 避免两份原文漂移（该约束出自派活交接包，票据正文无此表述） | 没枚举五类名称、没复制「看什么 / 出处」 |
| T2 | 五块用 `###` 子标题组织在同一个 `##` 节下 | 保持新节是单个顶层节，不打乱既有目录顺序 | 没拆成多个顶层 `##` 节 |
| T2 | 两段自述的落点定在票据文件末尾 | 票据只说「开工前填 / 收工时填」，未定落点；末尾追加是纯追加 | 没规定必须在文件头，没为自述另开文件 |
| T3 | §8 下六个子节的编号与标题（8.1–8.6） | 票据列了六块内容、没规定编号 | 没改 §1–§7 的标题、编号、顺序 |
| T3 | 用「见 §1」「见 §5」指回既有结论而不抄原文 | 避免两份原文漂移；票据反例把复述 §1–§7 列为不合格 | 没把 §1/§5 原文搬进 §8 |
| T4 | 「检查已兜住」只算例行层（CI / `--layer all`），deploy/fault/soak/real 按需层不算 | 按需层不在 CI 也不在 `--layer all`，删掉提醒就没人触发它 | 没按「verify.sh 存在该层」就一律判候选 |
| T4 | 无法从 `--list` 证实「某层是否已有断言」的，一律保守归保留 | 交接限定只读点名文件；外推易把「可能有检查」当成事实 | 没为凑候选把不确定条目写成删除候选 |
| T4 | 摘要放 `candidates.md` 顶部，未写 `ACCEPTANCE.md` | 交接的唯一写入路径不含 `ACCEPTANCE.md` | 没扩大写入路径（由规划方抄录进本包 §1.1） |
| T4 | 候选按 bullet 粒度（L187 的 ruff 与 pytest 子句合并为一行） | 票据检验对象写「每一条 bullet」 | 没把同一 bullet 拆成多条充数 |
| T4 | 候选文件加「结论摘要 / 例外直判保留 / 口径与范围 / 逐条判定」四节 | 记录例外命中与未入选依据，便于复核 | 没新增本仓库不存在的规则、工具或流程名词 |
| T4 | 跑 `--layer scripts` 时在 `var/evidence/` 落了一份证据目录 | verify 脚本既有行为，`var/` 已 gitignored | 没手工另写非清单文件、没清理脚本产物 |

## 4. 两轴评审发现（并列，不合并、不重排）

### 4.1 Spec 轴 · `dashscope/qwen3.8-flash`（异家族）

| 票 | 硬违规 | 判断项 | 无法判定 | 关键动作 |
| --- | --- | --- | --- | --- |
| T1 | **0** | 4 | 0 | §5 五类 + §6 八条的出处**逐条实际 grep**：D04/D11/D17/D19/D20/D22/D23、`AGENTS.md` 每个被点名的规则、`GLOSSARY.md` 术语、`docs/audit/CONTRACT.md`、`scripts/verify_mutation.sh` 全部真实存在，**无伪造节名或 D 号** |
| T2 | **0** | 7 | 1 | a–k 全一致（新节位置、五块、纯追加 47→50 行、既有节零改动、未抄五类原文、无历史叙述）；发现含**硬规则 2 违规**（阶段编号进长期文档）与**越界即红缺例外** |
| T3 | **0** | 5 | 1 | §1–§7 用 `cmp` + md5 逐字节验证未改；两个路由 id 经 `list_subagent_models` 实测存在；「用更强的模型审」只出现在否定句里 |

### 4.2 Standards 轴 + 意图一致性 · 规划方

- 红线全守住：`AGENTS.md` 零改动；`docs/tickets/p11-*` 与 `docs/history_docs/**` 零改动；无新增依赖；未提交。
- 出处抽查：`CODING_STANDARDS.md` §5/§6 引用的 D11/D19/D20/D22/D23、`GLOSSARY.md` 的幂等键与报告冻结、`AGENTS.md` §开发规范各条，规划方独立核过，与 Spec 轴结论一致。
- T4 候选 3 **否决**（能力指针被当成冗余规则）。候选 1、2 推理成立但**建议保留**（收益一行、代价是失去本地提前量与该行的映射职责）。
- 计数与结构达标：§6 恰好 8 条；`issue-tracker.md` 新节 5 个 `###`；`subagents.md` §8 有 6 个 `###`；既有节标题数与顺序未变。

## 5. 与提案的偏差（全部归因规划方，逐条见 `PROBLEMS.md`）

| # | 偏差 | 处置 |
| --- | --- | --- |
| 1 | T2 票据要求把「p12 及之后」写进长期文档 → 违反 `AGENTS.md` 硬规则 2 | 文档与票据均已订正为不带阶段编号的表述 |
| 2 | T1/T3 票据的「唯一写入路径」未排除票据自身两段自述 → 与 T2 新写的「越界即红」互斥 | `issue-tracker.md` 补例外并指回 `subagents.md` §8.3 |
| 3 | T3 票据把「互相覆盖」的出处写成 §2（实际在 §1） | `subagents.md` §8.2 已改为「见 §1」 |
| 4 | T2 票据一处「可以在句末加指针」与一处「diff 只有追加行」互斥 | 执行方放弃可选的指针，保住纯追加；规划方接受该处置 |
| 5 | T1 票据的 `grep -c '^- '` 数的是所有顶格 bullet，不是问题条数 | 本轮未改检查（计数恰为 8）；记为待修 |
| 6 | T2 票据 §验收 期望 `subagents.md` 无输出，与 T3 并行互斥 | 已授权执行方更正该行 |
| 7 | T4 票据未要求先区分 规则 / 指针 / 事实记录 | 规划方否决候选 3 |

**执行方侧的偏差**：T1 曾在「实现决定交代」里给出一条**未经实测的理由**（见 `PROBLEMS.md` §3），已由异家族评审发现并更正。除此之外未发现执行方偏离 spec。

## 6. 复跑命令与原始输出

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
cd '/root/better resume'
git diff --numstat CODING_STANDARDS.md docs/agents/issue-tracker.md docs/agents/subagents.md
git status --porcelain AGENTS.md docs/tickets/p11-resume-driven-questions docs/history_docs
grep -nE '^## ' CODING_STANDARDS.md docs/agents/subagents.md docs/agents/issue-tracker.md
awk '/^## 6/,0' CODING_STANDARDS.md | grep -c '^- '
bash scripts/verify.sh --layer scripts
cd apps/api && uv run python ../../scripts/verify_audit_evidence.py --structural
```

实测读数（2026-10-11 收口）：

- `git diff --numstat` → `57 0` / `50 0` / `48 0`（合计 **155 insertions, 0 deletions**）
- 冻结文件 `git status --porcelain` → **无输出**
- `CODING_STANDARDS.md` 二级标题 → §1(6) §2(18) §3(32) §4(39) **§5(50) §6(62)**；§1–§4 行号与内容未变
- `docs/agents/subagents.md` 二级标题 → §1(6) §2(12) §3(17) §4(23) §5(29) §6(34) §7(41) **§8(47)**
- `docs/agents/issue-tracker.md` 二级标题 → 目录约定(6) **票据与验收包的必填段(18)** 当某个技能说「发布到…」(68) … Wayfinding(90)
- §6 必答问题条数 → **8**
- `bash scripts/verify.sh --layer scripts` → `85 passed, 2 warnings` / `shell syntax ok` / `script syntax ok (23 python scripts…)` / `structure ok: 10 units / 122 issues / 341 citations` / **`ALL PASS (4 commands)`**
- `verify_audit_evidence.py --structural` → **`structure ok: 10 units / 122 issues / 341 citations`**，与开工前基线**逐字一致**
- 票据完整性基线：`var/p12-baseline/after-first-round.sha256`、`var/p12-baseline/final.sha256`（gitignored）

## 7. 未验证项（诚实清单）与待用户决定

### 7.1 未验证

- **T5 的主问题（§6 对 flash 有没有用）仍未回答**：任务失效，A 组不给 §6 也 2/2 抓住违规。要回答它需要重设计任务（违规必须埋得更深、或换成真实改代码的形态），那是一笔新的调用预算。
- **T5 只测了 §6 第 1 条**对应的违规形态，其余 7 条未测；每组 n=2。
- **隔离是 prompt 级**：污染检测器 A 组 0 命中，但无法排除「读了 §6 又用自己的话复述」（检测器只匹配特征串）。
- **§6 在真实评审轮里的表现未被覆盖**：T5 的任务形态是「审阅一份报告」，不是改代码。
- **新模板未在真实场景中用过**：§5 高风险面、§6 必答问题、§8 交接五栏、票据两段自述——本阶段自己用了后三者（并因此抓到 7 处规划方缺陷），但**没有在真实 `/code-review` 与真实代码阶段中验证过**。它们能不能真的降低你的验收负担，要等下一个代码阶段才有证据。
- **异家族评审只覆盖 T1/T2/T3**。T4 是分析类产出，由规划方直接复核，未做异家族评审。
- **未跑 `verify.sh --layer all`**（unit / coverage / contract 全量）与前端测试、契约三件套：本阶段纯文档，不涉代码与 REST 模型。只跑了 scripts 层 + 结构级审计。
- **「连续多轮不适用 → 删除候选」这条退出机制未演练**：它要等真实评审轮次累积，本阶段无法验证。
- **T4 的 9 条「保留但可自动化」未核实是否已有现存断言**：执行方未读 `apps/api/tests/**` 与前端测试。若某条已有会红的检查，它应改列为删除候选。
- **票据目录 untracked**，`git diff` 对票据无输出；票据完整性靠 `var/p12-baseline/*.sha256` 快照核验，不是 git。
- markdown 渲染未做人工/浏览器验证（T3 票据的表格后紧跟 `>` 行曾无空行，该元叙述行已按硬规则 2 移除）。

### 7.2 用户拍板结果（记进 `README.md` §1.4 Q6/Q7）

| # | 事项 | 决定 | 落地 |
| --- | --- | --- | --- |
| 1 | T5 的消融对象 | **(b)** 改为测「§6 必答问题机制对 flash 有没有用」 | `T5-rule-ablation.md` 重写；`README.md` §1.3 第 5 件事、§1.4 Q7、§4.1、§5 同步 |
| 2 | `AGENTS.md:26` 的「D01–D22」 | **可动** | 已改为「D01–D23」，与 `docs/DECISIONS.md:17`、:43 一致（`git diff --numstat AGENTS.md` = `1 1`） |
| 3 | T4 的 3 条删除候选 | **同意规划方推荐：全部保留** | 规则一条未删；候选 3 的否决理由记在 §1.1 与 `PROBLEMS.md` §6 |
| 4 | 「派活前给票据建 sha256 基线」 | **同意写进规范** | `docs/agents/subagents.md` **新增 §8.7**（含命令与「读数要抄进验收包」的要求） |
