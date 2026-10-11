# P11 验收包：简历驱动的分类出题（八股 / 项目 / 实习）＋ 按类报告

- **状态**：待用户验收（AI 不自行宣布完成；未提交、未推送）
- 提案：`README.md`（Q1–Q19 决策表）；票据：`T1`–`T10`（一票一文件）

## 1. 交付物对账（按提案 §3）

| 提案项 | 落地位置 |
| --- | --- |
| 语料 100–150 条 + 校验脚本 | `interview_engine/corpus/questions.json`（**120 条** / 10 topic × 12 / **43 个来源 URL**）；`apps/api/scripts/check_corpus.py` |
| corpus 子包与加载器 | `corpus/__init__.py`、`loader.py`（`Path(__file__)` 定位）、`matching.py` |
| sections 拆 key | `resume_parser/sections.py`：`internship` / `work` |
| prompt 传 key + 注入语料 | `interview_engine/prompts.py`：`render_context`（带 key）/ `render_corpus` / `render_mix` |
| `QuestionBatch` 加 category | `prompts.GeneratedQuestion.category`（受控枚举，非法值在 schema 层降为 None，不炸整批） |
| 引擎校验 + 规则回退 | `interview_engine/categories.py`：`decide_category` / `infer_category` |
| 配比计算 | `interview_engine/planning.py`：`plan_questions` |
| 报告按类聚合 | `interview_engine/report_service.py`：`category_breakdown` |
| 迁移 | `f4d2a6b8c1e3_question_category.py`（`interview_questions.category` + CHECK）、`a7c3e5b9d1f2_interview_type_enum.py`（旧自由文本归一为 `auto` + CHECK）、`b8e1f4c2d9a3_generation_notices.py`（`interview_sessions.resume_warnings` / `degraded_reasons`） |
| 前端 | 上传页侧重下拉（`InterviewIntroPage.tsx` + `interview/interviewTypes.ts`）、降级与解析质量提示（`interview/degraded.ts`：上传页预览卡片 + **面试间顶部提示条** `InterviewRoomPage.tsx` / `roomStore.ts`）、报告「按类给分」一节（`InterviewReportPage.tsx`） |
| 文档 | 本包、`PROBLEMS.md`；术语与决议在 spec 阶段已落（`GLOSSARY.md`、`docs/DECISIONS.md` D23） |

## 2. 红-绿证据（每票：先红后绿，命令可复跑）

| 票 | 用例文件 | 关键断言 |
| --- | --- | --- |
| T1 | `tests/resume_parser/test_sections.py` | 实习段 key=`internship`、工作段 key=`work`、两者并存得两条不同 key |
| T2 | `tests/interview_engine/test_prompts.py` | `render_context` 带 key；语料进 user 消息；无语料时无「参考题」小节 |
| T3 | `tests/interview_engine/test_corpus.py` | 正常可载；缺文件/坏 JSON/越界 schema/未知版本 → `CorpusError`（含路径） |
| T4 | 同上 | Redis 命中；`Java` 不命中 JavaScript；全不匹配返回空不报错；limit 与顺序稳定 |
| T5 | `tests/interview_engine/test_categories.py`、`test_question_service.py` | 非法/缺失 category → None；规则回退 project/internship/fundamentals；落库值 = 模型值或回退值 |
| T6 | `tests/interview_engine/test_follow_up_flow.py` | 追问继承主问题类别；主问题为 NULL 时追问也是 NULL |
| T7 | `tests/interview_engine/test_planning.py` | 实习+项目 → 1/2/2；只有项目 → 2 项目 3 八股；全无 → 5 八股；任意 count 各类之和守恒 |
| T8 | `tests/test_interview_api.py`、`test_migrations.py`、`test_categories.py` | 非法值 → 存 `auto`；显式值生效；缺省 `auto`；ORM/DB/枚举三方约束一致 |
| T9 | `tests/interview_engine/test_report_categories.py`、`tests/test_interview_report_api.py` | 按类均值与题数；<2 题 → `score=None` + 「样本不足」；零题类别也列出 |
| T10 | `tests/interview_engine/test_question_service.py`、`tests/test_interview_api.py` | 解析失败 → 201 + `degraded=true` + 仍出 5 题；正常不谎报；语料没匹配 → 另一种原因；坏语料 → `CorpusError` 且回滚 draft |

**行为变更（既有断言按提案改动，非放宽）**：`experience` → `work`/`internship`（`test_sections.py`、`test_parser.py`）；`test_unparsable_resume_returns_400_and_stays_retryable` → `test_unparsable_resume_degrades_instead_of_failing`（Q18）；`test_question_service` 的「解析失败先于供应商」用例改为降级用例。

## 3. 收口读数（本次实测）

| 检查 | 命令 | 读数 |
| --- | --- | --- |
| 后端全量 | `cd apps/api && uv run pytest -q --junitxml=/tmp/x.xml` | **944 passed** |
| 前端全量 | `pnpm -C apps/web test --run` | **183 passed**（25 文件） |
| 分层收口 | `bash scripts/verify.sh --layer all` | 16 条命令里 **15 绿**：命令 1–11 全绿（后端 944 / 前端 183 / ruff / alembic / 契约导出检查 / lint / tsc），第 12 条 `check:api` 红——它比的是 `gen:api && git diff --exit-code src/api/schema.d.ts`，**有未提交改动时必然红**（不是契约漂移：重生成后 `openapi.json` 与 `schema.d.ts` 哈希都不变）；13–16 由 `--layer scripts` 单独跑过：**ALL PASS (4 commands)**。提交后第 12 条自然转绿 |
| 语料结构 | `cd apps/api && uv run python scripts/check_corpus.py` | `entries: 120 | topics: 10 | sources: 43` → `corpus ok` |
| 契约三件套 | `export_openapi.py` + `gen:api` + `extract_api_index.py --check` | openapi.json 与 schema.d.ts 已同步；API index up to date |
| 迁移 | `uv run alembic upgrade head && uv run alembic check` | No new upgrade operations detected |
| 迁移演练（本次实测） | `uv run --with asyncpg python /tmp/migration_drill2.py`（一次性脚本，未入库） | 旧行 `interview_type='backend'` 升级后归一为 `auto`；CHECK 拒绝 `banana`（CheckViolationError）；`category` 列回退一步仍在、两步后消失；收尾 `upgrade head` + `alembic check` 通过 |
| 审计逐字级 | `python3 scripts/verify_audit_evidence.py --strict` | **122 / 0 / 0**；结构级 `--structural` = 10 units / 122 issues / 341 citations。实现与评审期的改动使引证移位，用一次性脚本重锚 25 条并重渲染 `docs/audit/MODULE-AUDIT.html` |
| 静态检查 | `ruff check` / `ruff format --check` / `eslint` / `tsc --noEmit` | 全绿 |

## 4. 与提案的偏差（**待你确认，未写进任何规则文档**）

1. **`interview_type` 取值是我定的**（spec 只说「改受控枚举 + 非法回退 auto」）：`auto` / `fundamentals` / `project` / `internship`；显式选某类时给该类 **3 个名额**（题量 5），不足则让位八股。下拉文案见 `interviewTypes.ts`。
2. **语料来源**：实际是 120 条 + **43 个官方文档页**（Python docs、Oracle JLS/GC tuning、MDN、redis.io、kafka.apache.org、RFC 9110/9111、kernel.org、man pages、cp-algorithms、Docker docs），不是中文八股汇总；每题仍逐条带 `source_url` + `fetched_at`。
3. **匹配算法**（spec 未规定）：技能串切词后与 topic/别名做**词级**比较（ASCII 整词、CJK 子串），因此 `Java` 不会命中 JavaScript 题；别名表在 `corpus/matching.py`。
4. **「按类给分」的口径**：`count` = 该类**有分数**的题数（含追问），`score` = 这些分数的均值（1 位小数），< 2 题 → 不给分 + 「样本不足」。
5. ~~降级不持久化~~ → **评审后已修**：降级原因与解析质量警告随 session 落库（迁移 `b8e1f4c2d9a3`），回放与面试间都能带出。
6. **语料注入上限**走新设置 `BR_CORPUS_LIMIT`（默认 24），已在 `.env.example` 记变量名。
7. `check_corpus.py` **不进 verify.sh / CI**；发布缺陷由 `tests/interview_engine/test_corpus.py` 的随包语料用例兜底（缺文件/坏 JSON/配额不足都会红）。
8. 提案 §4.1 的 T2 只要求「prompt 带 key」，本阶段**补了「语料进 prompt」的两条断言**（否则注入是无测试钉住的声称）。

## 5. 未验证项（诚实清单）

1. **提案 §4.2 的验收口径（传一份真 PDF → 每道题带可信类别 → 报告按类给分）没有端到端跑过**：现有证据全部来自 fake 网关 + 合成 PDF。真机跑需要真凭据、真简历与付费调用。
2. **真实模型是否稳定返回 `category`** 未测（提示词已要求，schema 容忍非法值）。
3. **浏览器手测**（侧重下拉、按类一节、面试间提示条的视觉与交互）未做——清单已写进 `docs/MANUAL-TESTING.md` §1.5（第 9–13 项），等你操作真浏览器。
4. 43 个来源 URL 中 `https://docs.docker.com/build/cache/` 在复核时本机抓不通（其余 42 个返回 200）；`docs.docker.com` 在本机时通时断。
5. **语料质量只做了结构校验 + 抽样阅读**，没有逐条人工评审；整理方自评最弱的三条：`kafka-producer-acks`、`os-proc-meminfo-pressure`、`js-event-loop-rendering`（细节部分依赖通用知识）。
6. ~~迁移的 `downgrade` 路径未逐条演练~~ → **本次已演练**（见 §3 最后一行：两步回退 + 旧值归一 + CHECK 拒绝）；仍未演练的是**生产数据量级**下的迁移耗时。
7. 一次全量跑里 `tests/test_distributed_flight.py::test_waiter_takes_over_after_the_owner_dies` 曾偶发红、重跑即绿（见 `PROBLEMS.md`），非本阶段改动面。
8. 另一次全量跑里 `tests/interview_engine/test_question_service.py::test_vendor_failure_rolls_the_session_back_to_draft` 曾偶发红（读不到 session 行）；单跑该文件与随后两次全量均绿，**未复现**，同样记为 flake（见 `PROBLEMS.md` §6）。

## 6. 复跑命令

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
cd '/root/better resume/apps/api' && uv run pytest -q --junitxml=/tmp/x.xml   # 942 passed
cd '/root/better resume' && pnpm -C apps/web test --run                        # 182 passed
bash scripts/verify.sh --layer all                                            # 全层
python3 scripts/verify_audit_evidence.py --strict                             # 122/0/0
```

## 7. 双轴评审（阶段 3 收尾；两轴并行、结论不合并）

### Standards 轴（对照 `CODING_STANDARDS.md` + `AGENTS.md` 开发规范 + Fowler 坏味道基线）

| # | 发现 | 处置 |
| --- | --- | --- |
| S1 | **硬性**：`main.py` 的 `ResumeParseError → 400` 处理器已成死代码（唯一解析调用点改走降级） | **已修**：删掉注册、`_bad_request` 与不再使用的 import |
| S2 | **硬性**：`planning._auto_mix` 里带 pragma 的 `else: break` 不可达 | **已修**：改成没有死分支的缩减写法 |
| S3 | 判断：`check_corpus.py` 的配额规则在测试里被重写一遍 | **已修**：测试只保留校验器不覆盖的断言（https / `fetched_at`） |
| S4 | 判断：前端 `THIN_SAMPLE` 与后端评语「双真相」，且用评语文本反推「无分数」 | **已修**：前端改按 `typeof score === "number"` 判断 |
| S5 | 判断：两个 `coerce_*` 同形 | 保留——fallback 语义不同（`auto` vs `None`），合并会掩盖差异 |
| S6 | 判断：枚举中文标签前后端各写一份 | 保留并记为已知重复（契约生成只覆盖类型、不覆盖文案） |
| S7 | 判断：边界把枚举退化成裸串（`interview_type: str`） | 保留——Q15 要求非法值回退而不是 422，边界必须收字符串 |
| S8 | 判断：`_select_corpus` 是一行转发的「中间人」 | 保留——它承载 Q19 语义（缺文件抛错 vs 空匹配降级），是有名字的缝 |
| S9 | 判断：新增深模块（`categories` / `planning` / `corpus`）不在审计单元里 | **未处理**：审计单元是模块设计审计的产物，补条目属另一件事（待办） |
| S10 | 判断：HANDOFF 里一句属回溯叙述 | **已修**：改写为纯状态描述 |

### Spec 轴（对照阶段 README 的 Q1–Q19 与 §4.1）

| # | 发现 | 处置 |
| --- | --- | --- |
| P1 | **最重**：Q18「降级前端明示」在真实路径不可见——上传成功立即跳转面试间，只有上传页预览卡片会显示 | **已修**：降级原因与解析质量警告**落到 session**（迁移 `b8e1f4c2d9a3`），面试间顶部显示提示条；回放同样带出（顺带消掉偏差 §4.5） |
| P2 | Q9 的「质量警告」缺失（解析器 `warnings` 没出到前端） | **已修**：同上，`resume_warnings` 随 session 返回并在面试间显示 |
| P3 | T8 缺「显式侧重 → 提示词真的变了」的链路证据 | **已修**：新增 `test_an_explicit_focus_reaches_the_prompt`（建会话 `project` → 提示词含「项目 3 道」） |
| P4 | 显式侧重的 3 个名额、题量 < 5 的缩减顺序、语料阈值严于 Q11 | 已在 §4 声明为**待确认偏差**（未写进任何规则文档） |
| P5 | Q16 的「题数」只算有分数的题 → 某类问 3 题只答 1 题时显示「1 题 / 样本不足」 | **待你拍板**：这是 §4.4 的偏差。若要「列清本场配比」，`count` 应改成该类被问到的题数（含未作答） |
| P6 | 解析失败时不再追加 `corpus_no_match` | 评审判定可接受（更严重的解析失败已覆盖该原因） |

> 两轴结论不合并、不重排：Standards 轴 2 条硬性（已修）+ 8 条判断题（3 条已修、5 条保留并说明）；Spec 轴 1 条最重（已修）、2 条缺失（已修）、1 条待拍板，其余为已声明偏差。

