# P11 提案：简历驱动的分类出题（八股 / 项目 / 实习）＋ 按类报告

> **依据**：一轮 `/grill-me` 拷问（2026-10-10）——事实由只读调研取得（结论均带 `文件:行号`），
> 决策由用户逐条拍板（Q1–Q19，见 §1.4 决策表）。
> **状态**：已实施，**待用户验收**——红绿证据、与提案的偏差、未验证项见同目录 `ACCEPTANCE.md`；
> 票据 `T1`–`T10` 一票一文件，难题台账见 `PROBLEMS.md`。

## 1. 范围

### 1.1 一句话

让面试题目**带可信类别**（八股 `fundamentals` / 项目 `project` / 实习 `internship`），
按简历内容决定**配比**，并让报告**按类给分**。

### 1.2 现状（已核实，不是推断）

| 现状 | 依据 |
| --- | --- |
| 上传窗口与 PDF 解析**都已存在**，且已串到出题链路 | `InterviewIntroPage.tsx:69`（`accept="application/pdf,.pdf"`）；`question_service.py:105` 调 `HybridResumeParser.parse()` |
| 出题**已经读简历**：`render_context` 注入 name/email/phone + 每段 title+≤12 bullets + ≤30 skills + ≤6 projects | `prompts.py:43-60` |
| 但**不传 section 的 key**，模型只看到标题文字 | `prompts.py:50-54` |
| `experience` 一个 key 同时吞掉「工作经历」与「实习经历」（首命中即止）→ 两者被**抹平** | `sections.py:15-22,46-51` |
| 题目**没有类别字段**，唯一类型字段是 `kind` ∈ {main, follow_up} | `orm.py:72-95`；`question_service.py:197` |
| 模型**本来就返回 `topic`**，但持久化时被丢弃 | `prompts.py:18-21` → `question_service.py:189-202` |
| 报告四维只按 主问题 / 追问题 两个桶聚合 | `report_service.py:251-257`；`dimensions` 是 JSONB（`orm.py:166-168`） |
| `interview_sessions.interview_type` 是**现成但闲置**的自由文本 | `interview.py:104-108`（存下+展示，未参与出题） |
| 题量恒为 5（前端不传 count；接口 default=5，clamp 1–10） | `interview.py:129`；`prompts.py:81-82` |
| 解析产物 `ResumeContext` **不落库**（只存 `resume_path`/`sha256`） | `orm.py:47-65`；`storage.py:17-33` |

### 1.3 本阶段要做的六件事

1. **类别**：题目带一个受控枚举 `category`（`fundamentals` / `project` / `internship`）。
2. **语料**：构建期整理一份 100–150 条的八股语料（带 `source_url`），运行时按简历技能过滤 top-N 拼进 prompt。
3. **解析**：`experience` 拆成 `work` / `internship`，并把 section 的 key 传进 prompt。
4. **配比**：引擎按简历内容算配比（实习 1 / 项目 2 / 其余八股，题量仍 5），用户可在上传页覆盖。
5. **报告**：雷达保持四维，**另开一节**按类给分。
6. **降级**：解析失败或语料没匹配上时照常开面试，但**明示**降级。

### 1.4 决策表（Q1–Q19 全量落地）

| # | 决策 | 选择 |
| --- | --- | --- |
| Q1 | 八股/项目/实习 的形态 | **(a) 题型标签**，同场混排 + 报告按类给分（不做两种模式、不做自动编排） |
| Q2.1 | 语料何时获取 | **(A) 构建期**搜集并提交进仓库；运行期只读本地，**不联网** |
| Q2.2 | 语料缺失/超时 | 降级为纯 LLM 生成 + **明示「本次未使用语料」** |
| Q3 | 实习经历 | **(b) 只拆 key + 把 key 传进 prompt**；**不**新建结构化 `Internship` 模型 |
| Q4 | 解析质量差 | **(b) 降级 + 明示警告**（不上 OCR、不拒绝重传） |
| Q5 | 验收口径 | **(a)** 每道题带可信类别 + 报告能按类给分 |
| Q6 | 分类法 | **(a) 三个一级类**；语料自带 `topic` 二级标签，**只用于检索**，不进报告/配比 |
| Q7 | 报告怎么落「类」 | **(c) 雷达保持四维**，另开一节按类给分 |
| Q8 | 配比谁定 | **(c)+(b)**：默认引擎按简历算，上传页可覆盖 |
| Q9 | 解析结果可编辑 | **(b) 只读** + 质量警告 |
| Q10 | 类别由谁判定 | **(c)** 模型返回（`QuestionBatch` 加字段）+ 引擎枚举校验 + **规则回退** |
| Q11 | 语料规模 | **(a) 100–150 条**，覆盖 8–10 个常见技术栈，逐条带 `source_url`/`fetched_at` |
| Q12 | 追问的类别 | **继承主问题**（零成本；顺带得到「八股深度/项目深度」） |
| Q13 | 面试中类别可见性 | **不可见**；报告里列清本场类别与配比（不做演示模式开关） |
| Q14 | 语料怎么进 prompt | **(a)** 按简历 skills 标签过滤取 top-N（默认 20–30，可配）；**不引向量检索**（D03） |
| Q15 | `interview_type` | **改受控枚举**（迁移 + 前端下拉），非法值回退 `auto` |
| Q16 | 按类给分算什么 | **分数 + 题数 + 一句评语**；某类 **< 2 题时不显示分数**，写「样本不足」 |
| Q17 | 默认配比与题量 | 题量 **5**：有实习→1 实习，有项目→2 项目，其余补八股；缺类则名额让给八股 |
| Q18 | 简历没解析出东西 | **照开**：纯 LLM 出通用八股，响应带 `degraded` + 原因，前端明示 |
| Q19 | 缺文件 vs 没匹配 | **缺文件 / 坏 JSON = 大声失败**（发布缺陷，必须红）；**过滤后没匹配 = 降级** |

### 1.5 语料落位（事实已核实，无需再定）

- 路径：`apps/api/src/better_resume/interview_engine/corpus/`（子包，含 `__init__.py` + 加载器），
  加载器用 `Path(__file__)` 定位，**不用相对 cwd**。
- **`pyproject.toml` 与 `Dockerfile` 都不用改**：hatchling 默认打包包内数据；本地是 editable（`.pth` 指向 `apps/api/src`）；
  镜像 `Dockerfile:18` 的 `COPY src ./src` 已覆盖（构建上下文 `./apps/api`，见 `compose.yaml:81-82`）。
- **不能放 `data/`**——它是 `.gitignore:30` 的忽略目录，连 git 都进不去。
- 既有守卫逐一核对过，新增此子包**不会**让 `test_skills_index` / `test_source_hygiene` / `check_scripts` /
  `check_coverage_floors` / `verify_audit_evidence` 变红。

## 2. 不做（本阶段明确排除）

- **不做 OCR**（扫描件一律走降级路径）。
- **不做运行期联网搜索**（Q2.1 选了构建期；接口留缝，但本阶段不开）。
- **不引向量检索/第三存储**（违 D03）。
- **不做解析结果编辑**（Q9；要回写、重算 sha256、重出题，链路长且不阻塞验收）。
- **不把「工作经历」单列一类**（只三个一级类）。
- **不做类 × 四维矩阵**（Q16；5 题分 3 类，小样本矩阵全是噪声）。
- **不做「演示模式」开关**（Q13；面试中不显类别）。
- **不改默认题量 5**（Q17）。
- **语料不是题库**：它只给模型当参考，不做机械抽题，也不承诺覆盖度。

## 3. 交付物

| 类别 | 内容 |
| --- | --- |
| 语料 | `interview_engine/corpus/*.json`（100–150 条，含 `id/topic/question/source_url/fetched_at`）+ 生成/校验脚本 |
| 代码 | corpus 子包与加载器；`sections.py` 拆 key；`prompts.py` 传 key + 注入语料；`QuestionBatch` 加 `category`；引擎校验+回退；配比计算；`report_service` 按类聚合 |
| 迁移 | `interview_questions.category`（可空，历史行为 NULL=未分类）；`interview_sessions.interview_type` 转受控枚举 |
| 前端 | 上传页 `interview_type` 下拉；预览**只读**+质量警告；降级明示；报告新增「按类」一节 |
| 文档 | 本 README、`ACCEPTANCE.md`、`PROBLEMS.md`（按需）；`GLOSSARY.md` 术语；`DECISIONS.md` D23 |

## 4. 测试与验收口径

### 4.1 红-绿垂直切片（先写会红的用例）

| # | 用例 | 断什么 |
| --- | --- | --- |
| T1 | 章节拆分 | 简历含「实习经历」→ 该 section `key == internship`；含「工作经历」→ `work`；**两者都有 → 两条不同 key 的 section** |
| T2 | prompt 带 key | `render_context` 输出含该段类型标签（字符串断言） |
| T3 | 语料加载 | 正常文件可载；**文件缺失抛错**；**JSON 损坏抛错**（Q19） |
| T4 | 语料过滤 | 简历技能含 Redis → 候选中必含 Redis 题；技能全不匹配 → 返回空且**不报错**（Q14） |
| T5 | 类别落库 | 模型返回合法枚举 → 落库；**非法/缺失 → 规则回退**（引用 project → `project`；实习段 → `internship`；否则 `fundamentals`） |
| T6 | 追问继承 | 追问行的 `category` == 主问题行的 `category`（Q12） |
| T7 | 配比 | 有实习+项目 → 1/2/2；只有项目 → 项目 2、其余八股；全无 → 5 道八股（降级） |
| T8 | `interview_type` | 非法值 → 回退 `auto`；显式值 → 生效（Q15） |
| T9 | 报告按类 | 聚合正确；**某类只有 1 题 → 不出分数**、出「样本不足」（Q16） |
| T10 | 降级 | 解析失败 → 响应带 `degraded` + 原因，且**仍能出题**（Q18） |

### 4.2 验收（Q5）

传一份**真 PDF** → 每道题在库里带可信类别 → 报告能按类给分。

### 4.3 复跑命令

```bash
cd apps/api && uv run pytest -q --junitxml=/tmp/x.xml     # 例数看 xml 读数，别抄进文档
cd '/root/better resume' && pnpm -C apps/web test --run
bash scripts/verify.sh --layer all                        # 收口：全层
```

回归底线：既有后端 887 例与 `--layer all` 全绿**不得变红**。

## 5. 预估

| 工作包 | 规模 | 说明 |
| --- | --- | --- |
| 语料搜集与整理 | **L** | 最不确定：搜 8–10 个技术栈、逐条记 `source_url`、人工过一遍质量 |
| 语料加载器 + 过滤 | S | 纯函数 + 两个拒绝路径的测试 |
| 章节拆分 + prompt | S | `sections.py` / `prompts.py` 各一处 |
| 类别（schema+校验+回退+迁移） | M | 含 `QuestionBatch` 契约变更与报告聚合扩展 |
| 配比 + `interview_type` 枚举 | M | 含前端下拉与迁移 |
| 报告按类一节 | M | 后端聚合 + 前端展示 + 「样本不足」规则 |
| 降级路径 + 前端明示 | S | 与既有 503/警告模式一致 |
| 验收包 | S | `ACCEPTANCE.md` + 证据 |

**最大风险**：① 语料质量（搜来的题如果本身就是烂题，模型会被带偏）；② 类别判定的一致性
（模型偶尔把项目题判成八股）——所以 Q10 必须有规则回退，且回退逻辑要单独可测。

## 6. 需要用户决定的问题

**无。** Q1–Q19 已在 grill 阶段逐条拍定（见 §1.4）。

以下三条是低风险默认，若无异议即按此执行（有异议请直接说，我改）：

1. 阶段目录名取 `p11-resume-driven-questions`（要改说一声）。
2. 语料来源用公开面试题汇总，**逐条带 `source_url`**；不指定站点的话我自己挑。
3. 阶段实施完成后，把「语料怎么更新」写进 `docs/HANDOFF.md`（与既有环境事实同一处）。
