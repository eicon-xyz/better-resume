# P13 验收包：假模型驱动的黄金路径 E2E

- **状态**：待用户验收（AI 不自行宣布完成；未提交、未推送、未开 PR）
- 提案：`README.md`（§6 决策表 Q1–Q4）；票据：`T1`–`T5`（一票一文件，`Status: done（红绿已过，待用户验收）`）；难题台账：`PROBLEMS.md`
- 执行方：`opencode-go/deepseek-v4.1-flash`（5 张票 + 1 个修复轮）
- Spec 轴评审：`dashscope/qwen3.8-flash`；Standards 轴 + 意图一致性：`dashscope/qwen3.8-flash`（按 `docs/agents/subagents.md` §8.5，规划/验收方与执行方同家族，双轴均外派）；主验收方只做家族无关的机械核对
- 读数口径：**AI 自证读数（§6）**与**用户在宿主机跑的读数（§7.2，待回填）**分表列示（Q3）

## 1. 交付物对账（按提案 §3）

| 提案项 | 落地位置 | 读数 |
| --- | --- | --- |
| 假供应商产出合法 `category`（并保留无 category 形态） | `apps/api/scripts/fake_openai.py` | `CATEGORY_VALUES` 三枚举循环；`NO_CATEGORY_MARKER`（prompt 含标记 → 不给 category，D23 回退形态）；两形态均可显式选择 |
| 收紧后的防漂移守卫 | `apps/api/tests/test_fake_openai.py` | 反射扫描四份契约的**受控枚举字段**（存在性 + 合法值，递归子模型）；缺 `category` 必红（主验收方变异复现 3 红） |
| 可断言的黄金路径（假模型 + 走 nginx + 退出码） | `apps/api/scripts/interview_smoke.py` | 一份实现两种调用：真模型打印（基线行为，`m2-smoke`/`cv.pdf`）；`--model smoke-fake --assert` 断言 + 非 0 退出；`--expect-questions` 可注入期望演示红 |
| 降级路径 fixture 与断言 | 同上 + `apps/api/tests/test_interview_smoke_script.py` | 四场景（golden / no-text-layer / unmatched-corpus / no-category）；降级原因与 `resume_warnings` 明示 + **落库**（DB 级断言，F2）；类别三枚举 + 追问继承 + 按类聚合 + 「样本不足」 |
| 新层接线与层图 | `scripts/verify.sh` + `apps/api/tests/test_verify_script.py` | `e2e` 层（Q1），`--list` 由层计划渲染、层图逐字钉住；不进 `all`、不进 CI 双 job |
| 手测清单重划 | `docs/MANUAL-TESTING.md` §1.5 与 §4 | 每项拆「已自动化（层/命令）」与「仍须手测（渲染/真模型）」；§4 新增 `e2e` 行；无虚标（第 9 项语义如实标未纳入 e2e） |
| 验收包 | 本文件 | 含变异演示红输出、AI 自证读数、用户待跑清单 |

Q2 兑现核对：假供应商两种形态**都被 e2e 层默认四场景跑到**（golden 走「给 category」主路径、no-category 场景走 D23 规则回退形态；单测 `test_default_assert_mode_runs_every_scenario` 钉住默认全覆盖）。

## 2. 改动面与高风险面自查

### 2.1 `git diff --stat` 原始输出（工作区 vs 基线 commit `05d3d8b`）

```
 apps/api/scripts/fake_openai.py                    |  31 +-
 apps/api/scripts/interview_smoke.py                | 972 ++++++++++++++++++++-
 apps/api/tests/test_fake_openai.py                 | 133 ++-
 apps/api/tests/test_verify_script.py               |   3 +-
 docs/MANUAL-TESTING.md                             |  17 +-
 docs/tickets/p13-golden-path-e2e/T1-….md           |  26 +-
 docs/tickets/p13-golden-path-e2e/T2-….md           |  31 +-
 docs/tickets/p13-golden-path-e2e/T3-….md           |  19 +-
 docs/tickets/p13-golden-path-e2e/T4-….md           |  23 +-
 docs/tickets/p13-golden-path-e2e/T5-….md           |  21 +-
 scripts/verify.sh                                  |  15 +-
 11 files changed, 1236 insertions(+), 55 deletions(-)
```

另有 1 个新增未跟踪文件：`apps/api/tests/test_interview_smoke_script.py`（692 /root/better resume/apps/api/tests/test_interview_smoke_script.py）。票据的 `-1` 删除行各 1 条 = 主验收方翻 `Status:` 行（正文零删除）；`interview_smoke.py` 的 `-26` = 真模型旧 `run()`/`__main__` 被一份实现两种调用替换。

### 2.2 与各票声明的唯一写入路径逐条比对

| 票 | 声明的写入路径 | 实际 | 判定 |
| --- | --- | --- | --- |
| T1 | `apps/api/scripts/fake_openai.py` + `apps/api/tests/test_fake_openai.py` | 恰好这两个 | 一致 |
| T2 | `apps/api/scripts/interview_smoke.py`（+括注可加 `tests/test_interview_smoke_script.py`） | 脚本 + 新增测试文件 | 一致 |
| T3 | `scripts/verify.sh` + `apps/api/tests/test_verify_script.py` | 恰好这两个 | 一致 |
| T4 | `apps/api/scripts/interview_smoke.py` 与所需 fixture | 脚本 + **T2 的测试文件**（派工口径扩展，见 §5-6） | **口径扩展，待用户确认** |
| T5 | `docs/MANUAL-TESTING.md` | 只有它 | 一致 |
| 修复轮 | 四个允许文件（脚本/测试/手测文档/fake 注释） | 恰好这四个（mtime 佐证） | 一致 |

票据自身末尾的「意图复述」「实现决定交代」按 `docs/agents/subagents.md` §8.3 不计入写入路径。冻结面零改动：`AGENTS.md`、`CODING_STANDARDS.md`、`docs/agents/**`、`docs/tickets/p11-*`、`docs/tickets/p12-*`、`docs/history_docs/**`、`apps/api/src/**`、`apps/api/migrations/**`、`apps/web/**`、`compose.yaml`、`.env.example`、依赖清单——`git status --porcelain` 对以上全部无输出。

### 2.3 按 `CODING_STANDARDS.md` §5 五类逐类勾（Standards 轴逐类核过，主验收方复核）

| 类 | 碰了 / 没碰 | 证据 |
| --- | --- | --- |
| 权限与认证 | **没碰** | `identity/`、`http/` 零改动；脚本只消费既有会话端点 |
| 状态变化与幂等 | **碰了（读侧）** | 幂等键范围未变（重试复用同一 `request_id`）；报告冻结/题级锁未绕过；脚本断二次 finish 同分（F4 已补会红证明） |
| 并发与重试 | **碰了（客户端侧）** | 手写 429 按 `Retry-After` 退避（上限 5），未引重试库；两模式都打印提示（F1） |
| 数据一致性与迁移回滚 | **没碰** | 无新迁移、无模型改动；`alembic check` 面未动 |
| 对外契约与降级语义 | **碰了（消费侧）** | REST 模型未改（契约三件套哈希不变）；断言读的都是契约字段；降级明示 + 落库双断言（F2） |

## 3. 自行拍定的决定（跨票聚合，与「偏差」并列不合并）

| 票 | spec 未覆盖、自行拍定的决定 | 为什么这么拍 | 明确没做的 |
| --- | --- | --- | --- |
| T1 | 切换标记 `NO_CATEGORY_MARKER = "不给出 category"`（prompt 嗅探切换） | 沿用 `scene_for` 的嗅探风格，不引新协议 | 没造正向标记 |
| T1 | 题间循环三枚举（每类都出现） | 票只要求落在枚举内；fake 不解析配比 | 没按配比分配 |
| T1 | 守卫反射扫四份契约 + 递归子模型 | 「契约里所有受控枚举字段」的读法 | 没写字段名清单 |
| T1 | 守卫读原始 payload（存在性+合法值） | 可空字段缺失也能解析，堵漏检 | 没只断「能解析」 |
| T1 | 「新增字段→红」用测试内 `_ExtendedQuestion` 探针 | 红线禁改真实契约 | 没改契约制造红 |
| T1 | 无 category 形态豁免守卫，单独用例覆盖 | 回退形态本就不该带 category | 没接进 verify 层 |
| T2 | `--assert` 必须配 `--model smoke-fake`（否则退出 2） | 证据诚实的硬门槛 | 没留 allow-real 旁路 |
| T2 | `--count`（请求）与 `--expect-questions`（期望）分开 | 期望驱动请求则坏期望演示永不红 | 没反写期望 |
| T2 | 真分支保留 8040/count=3/6 次上限 | 「行为与现在一致」 | 没把真模型改 5 题 |
| T2 | 每步 2xx 命名检查 + 连接异常命名 | 「每步失败能指名」 | 没吞异常 |
| T2 | DB 探针可注入、失败时给可复制 psql | 要真查但单测不能依赖 docker | 没在单测连 docker |
| T2 | 报告不断言 `summary` 非空 | 异步 worker 补总结 | 没轮询 worker |
| T2 | 真模型路径不新增 usage 打印 | 现状无 usage（票面括注有误，见 §5-1） | 没编造 usage |
| T3 | e2e 插 `LAYER_ORDER` 的 deploy 之后 | 既有层相对顺序不动 | 没重排层 |
| T3 | e2e 用 `all:` 标签（scope 不裁剪） | 与 deploy/fault/soak 同族 | 没做 scope 分支 |
| T3 | `--list` 不加注释行 | 避免第二份口径 | 没手写文案 |
| T4 | 四场景默认全跑，`--scenario` 仅过滤 | 共享契约默认全覆盖 | 没留默认关闭分支 |
| T4 | 无文本层 fixture = reportlab 空页图形 | 与手测第 10 项一致 | — |
| T4 | 无关技能 fixture = ASCII 逗号单行 | 遵循 P11 台账的 CJK 分隔符坑 | — |
| T4 | 无 category = 简历文本注入 `NO_CATEGORY_MARKER` | 不改引擎/fake 即可选形态 | 没改引擎迁就 |
| T4 | 每次跑唯一 `run_user` 并打印 | 唯一 run id | 没做行清理（§8-3） |
| T4 | 429 按 `Retry-After` 退避（上限 5，复用 request_id） | answer 桶 2/s，快速行必被限流 | 没改限流配置 |
| T4 | 降级码本地常量 + 漂移守卫 | 预期来自契约不按返回反写 | — |
| T5 | 第 9 项语义标「未纳入 e2e 断言」 | 无断言不虚标 | 没拿 unit 覆盖当理由 |
| T5 | §1.5 改四列表；§4 e2e 行触发写「仅手动」 | 逐项点名；触发如实 | 没写 nightly、没抄命令原文 |
| 修复轮 | F2 探针返回结构化快照；空题目行集判失败 | 失败诊断与成功断言复用同一探针；空集不叫落库 | 没加 `--json`/证据参数 |
| 修复轮 | F2 缺探针显式 `SKIPPED` 不判失败 | 单测无 docker | 没静默跳过 |
| 修复轮 | F3b 选改措辞而非补手测步骤 | 非法值回退已有 unit 覆盖，手测无低成本路径 | 没改 §1.5 其它行 |
| 修复轮 | F5 守卫用真源符号（签名默认值/枚举/标签表） | 不抄字面量 | 没把测试文件自身副本纳入守卫 |

## 4. 两轴评审发现（并列，不合并、不重排）与处置

### 4.1 Spec 轴 · `dashscope/qwen3.8-flash` —— 硬违规 8 / 判断项 16 / 无法判定 1

| # | 发现（票/文件） | 处置 |
| --- | --- | --- |
| 硬1 | 共享 `RESUME_LINES` 技能行顿号→逗号，牵动 real/deploy/fault 三层共用 fixture，两票未交代 | **保留 + 记偏差**（§5-7，待用户确认）；Standards 轴实测两版解析等价 |
| 硬2 | 真模型路径登录身份变随机（`m2-smoke-<hex>`） | **已修 F1**（恢复 `m2-smoke`）+ 红-绿用例钉住 |
| 硬3 | 真模型上传文件名变 `golden.pdf` | **已修 F1**（恢复 `cv.pdf`） |
| 硬4 | T2 红线「两种调用都被某一层跑到」未兑现（打印形态不在任何层） | **待用户拍板**（§8-1）；规格自相矛盾（PROBLEMS §4） |
| 硬5 | T4「落库」断言在 diff 不存在；MANUAL-TESTING 已标 e2e 覆盖 | **已修 F2/F3**（DB 级落库断言 + 文档措辞） |
| 硬6 | T4 验收要求的 `var/evidence/<ts>-e2e/` 不存在 | **口径澄清**（PROBLEMS §5）：`verify.sh` 通用 runner 自动落该目录，e2e 层跑过即有 |
| 硬7 | MANUAL-TESTING:55「resume_warnings 落库」虚标 | **已修 F3** |
| 硬8 | 验收包不存在 | **本文件**（收口交付物，非执行方欠账） |

判断项要点处置：`fake_openai` 旧守卫自述注释（**已修 F6**）；守卫嵌套缺席不查（记局限）；T1 复述把「被层跑到」推给后续票（阶段层面成立，e2e+单测已覆盖）；429 退避两模式生效而交代表只写断言客户端（**已修 F1b** 可见性 + §5-8）；`open_timeout` 票面措辞与 httpx 不匹配（记票面措辞问题，实现满足意图）；T3 目标句「nightly 能跑到」未兑现（**待用户拍板** §8-6）；T3 复述描述了当时不存在的 T4 状态（记自述瑕疵）；README 净结果句与交付出入（§5-5）；手测第 54/56 项措辞（**已修 F3**）。

### 4.2 Standards 轴 + 意图一致性 · `dashscope/qwen3.8-flash` —— 越界 1 / 硬违规 4 / 判断项 10 / 无法判定 4

| # | 发现 | 处置 |
| --- | --- | --- |
| V1 | 票据 `Status:` 行被改写且裸 `done` 不在词表（主验收方所为） | **已修**：五票补 P11 式限定 `done（红绿已过，待用户验收）`；简报口径同步更正 |
| V2 | MANUAL-TESTING:55 写了脚本里不存在的断言 | **已修 F2/F3** |
| V3 | 打印/真模型形态不在任何层（=Spec 硬4） | **待用户拍板**（§8-1） |
| V4 | 「证据目录」无实现（=Spec 硬6） | 口径澄清（PROBLEMS §5） |

判断项要点处置：真模型三处未交代改动（**已修 F1**，§4.1 硬2/3）；共享 fixture 爆炸半径（§5-7）；手抄常量缺守卫（**已修 F5**）；`test_fixture_grounds` 快照式期望一处（记残留）；FakeStack 第二份形状实现（记局限，PROBLEMS §13）；二次 finish 断言无会红检查（**已修 F4**）；「样本不足」真实栈触发面（no-category 场景全 fundamentals 会触发，e2e 跑即证）；T4 用例写 T2 文件（**待用户确认** §8-2）；e2e 有 compose_smoke 种行前置（注释已如实）；每跑留行不清理（**待用户拍板** §8-3）。

### 4.3 修复轮复核 · `dashscope/qwen3.8-flash`（只核自述 vs diff）

结论：**六项声称改动全部真实**，红-绿引文与用例断言三方互证、终态读数有实物；不一致 4 处均轻微、无法判定 1 处（已全部查清）。

- 不一致（轻微）：① `probe_db_rows` 的「docker 可用但 sessions 行缺失→SKIPPED」边界未写进自述——**实质问题，已由微型修复轮 2 修正**（SKIPPED 只留给真·无 docker，缺行改判 FAIL `db: session row is persisted`）；② 中间用例计数 21→25→28 与章节顺序不能同时为真；③ F5 红引文断言操作数次序与用例正文相反；④ 自述「9 个 M」与自列 11 行相抵、mtime 时间戳与现值不符——②③④ 记档不返工（PROBLEMS §17）。
- 无法判定 1 处：`interview_smoke.py` 21:25:58 报告后写入归责——**已查清**：主验收方变异演示的 `cp` 恢复（`cmp` 一致）；同类 mtime 噪声另记 PROBLEMS §16（`redis_buckets.py` 幂等刷新、内容与索引逐字节一致、写入者未定位）。
- 主验收方对修复轮 1/2 共亲做三场变异（常量 2→3、落库比较恒真、session 行缺失分支恒通过）+ 修复轮 2 的 reasons 半边用例由执行方变异证明。另记一次主验收方自己的操作失误：变异脚本的 heredoc 单引号字符串被换行撑破导致 python 编译期静默死亡、变异从未执行（已改正写法并补做，见回报记录）。

## 5. 与提案/票据的偏差（全部待用户确认，不追认成规则）

| # | 偏差 | 归因 | 处置 |
| --- | --- | --- | --- |
| 1 | T2 票括注「打印 + usage」与现状不符 | 票据文字 | 记缺陷；是否补 usage 待拍板 |
| 2 | 真模型形态不在任何层，「两种调用都被层跑到」只兑现一半 | 提案 §1.2/§1.3 自相矛盾 | 待拍板（§8-1） |
| 3 | T4「落库」断言一度收窄为 HTTP 往返 | 执行方收窄未上报 | 已修 F2 补齐 |
| 4 | T3 目标句「nightly 与本地收口都能跑到」中 nightly 未接 | T3 红线禁改 workflow | 待拍板（§8-6） |
| 5 | README §1.4 净结果「语义断言全部搬进 CI/nightly」与交付出入（e2e 手动、第 9 项未搬） | 提案愿景句早于 Q 拍板 | 记偏差 |
| 6 | T4 用例写进 T2 的测试文件 | 派工口径扩展（主验收方） | 待确认（§8-2） |
| 7 | 共享 `RESUME_LINES` 技能行顿号→逗号未在交代表交代 | 执行方 | 保留 + 待确认（§8-4） |
| 8 | 429 退避在真模型路径也生效（基线无重试） | T4 加、修复轮保留 | 保留 + 待确认（§8-5）；真机跑需要它过限流桶 |

## 6. AI 自证读数（主验收方亲自重跑，2026-10-11）

```bash
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR='/root/better resume/.cache/uv'
cd '/root/better resume/apps/api'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
```

| 命令 | 读数（junitxml / 原始输出） |
| --- | --- |
| `uv run pytest -q tests/test_fake_openai.py` | `tests=11 failures=0 errors=0 skipped=0` |
| `uv run pytest -q tests/test_interview_smoke_script.py` | `tests=31 failures=0 errors=0 skipped=0`（T4 后 20 → 修复轮 1 后 28 → 修复轮 2 后 31） |
| `uv run pytest -q tests/test_verify_script.py` | `tests=27 failures=0 errors=0 skipped=0` |
| `uv run pytest -q`（全量） | `tests=981 failures=0 errors=0 skipped=0`（修复轮 2 后；每轮均重跑确认。一轮曾 1 failed = `test_distributed_lock::test_bounded_wait_raises_a_clear_error` 时序 flake，单跑 3/3 绿、本阶段改动零接触该模块） |
| `bash scripts/verify.sh --layer scripts` | `ALL PASS (4 commands)`；`86 passed`；审计结构级 `10 units / 122 issues / 341 citations` |
| `bash scripts/verify.sh --layer all` | **`ALL PASS (16 commands)`**（终轮证据 `var/evidence/20261011T140629Z-all`：后端 **981 passed**、前端 25 文件 **183 passed**、契约/静态/迁移全过、审计结构级 10/122/341）。口径：共 4 轮，2 轮全绿、2 轮被同一条**存量 flake**（`test_distributed_lock::test_bounded_wait_raises_a_clear_error`，PROBLEMS §18）打断——红的两轮其余 15 条命令与 980+ 用例同样全绿，该 flake 与本阶段改动无关 |
| `verify_audit_evidence.py --strict` | `verifiable: 122 partial: 0 unverifiable: 0`（exit 0） |
| `ruff format --check . && uv run ruff check .` | `267 files already formatted` / `All checks passed!` |
| 前端（`--layer all` 内 vitest） | `Test Files 25 passed` / `Tests 183 passed` |

**变异证明（全部由主验收方亲自做，非执行方自述）**：

1. T1：删掉 fake payload 的 `category` → **3 红**（`GeneratedQuestion.category: missing` / KeyError / 形态选择用例），恢复绿；
2. T3：`verify.sh` 回退 HEAD → **2 红**（`missing layer header: e2e` / `unknown layer: e2e`），恢复绿（`numstat 11/4` 一致）；
3. T4：汇总退出码打成恒 0 → **10 红用例全炸**（恰好=全部「必须红」用例），恢复绿；
4. 修复轮 F5：`MAX_FOLLOW_UP` 副本 2→3 → 常量守卫红（`assert 2 == 3`），恢复绿；
5. 修复轮 F2：落库比较两半打恒真 → `test_a_wrong_database_session_row_is_red` 红，恢复绿；
6. 修复轮 2：`db: session row is persisted` 分支打成恒通过 → `test_a_missing_session_row_from_a_working_probe_is_red` 红（exit=1），恢复绿。

## 7. 未验证项（诚实清单）与用户读数（Q3：待你在宿主机跑并回填）

### 7.1 未验证 / 局限（2026-10-12 收口更新）

1. ~~compose/nginx 端到端读数~~ **已跑通并回填 §7.2**（四场景全 PASS + 8 条 db 断言 + 证据目录 + 红演示 + psql 四行）。
2. 执行方自证的本地实跑（uvicorn + 本地 fake + redis）**无留存产物**、跑后已清库，无法独立复核（PROBLEMS §6）——现已被 §7.2 的真栈读数取代。
3. ~~probe_db_rows 真库解析未验证~~ → **验证时发现是坏的**（psql `-c` 不插值，PROBLEMS §19）→ 修复轮 3 修复，真栈 8 条 db 断言全 PASS。
4. 真模型路径（真 key）未跑：429 退避只在 FakeStack 与假供应商 e2e 验证；usage 打印按拍板不补（§8-8）。
5. 测试文件自身的契约常量副本未纳入漂移守卫（修复轮明确没做）。
6. ~~FakeStack 形状只能由真栈暴露~~ → 真栈 e2e 已跑通（REST 契约接受其形状）；残余风险仅限未覆盖的响应分支。
7. 「样本不足」分支已在真栈触发并断言通过（no-category 场景全 fundamentals）。
8. `test_distributed_lock` 时序 flake 仍在（PROBLEMS §18，与本阶段无关，建议另票用注入时钟修）。
9. 「有 docker 且 sessions 行缺失」的真实路径只由 monkeypatch 证明（单测层），真栈没造过这种状态。

### 7.2 宿主机读数（2026-10-12 回填；Q3 的「用户跑的读数」栏，本次经用户指令由 AI 在宿主机执行）

| 命令 | 读数（原始输出要点） |
| --- | --- |
| `bash scripts/compose_smoke.sh` | **ALL CHECKS PASSED**（起栈 + 种 `smoke-fake` 行 + 部署面全套检查；buildx 首次在沙箱被拒（`~/.docker/buildx/activity` 写入拒绝），按流程提权后通过） |
| `bash scripts/verify.sh --layer e2e` | **EXIT=0，四场景全 PASS**（golden / no-text-layer / unmatched-corpus / no-category），走 nginx + 双 api 副本 + 重建假供应商；含 **8 条 `db:` 落库断言对真实 Postgres 全 PASS**。证据：`var/evidence/20261012T025634Z-e2e/`（首轮 `…024643Z-e2e` 的 db 断言因 psql 缺陷 SKIPPED → 修复轮 3 修复后本轮真跑，见 PROBLEMS §19） |
| 红演示 `--expect-questions 4` | **RED_EXIT=1**，`FAIL questions: contract count: expected 4, got 5`（含原始响应与 psql inspect 行） |
| psql 查库（`run_user=m2-smoke-5e322e51`） | **4 行与预期逐字一致**：`[]/[]`、`["resume_unparsable"]/[]`、`["corpus_no_match"]/["no_sections_detected","no_contact_found"]`、`[]/[]`；`question_count` 全 5 |
| `bash scripts/kill_instance_drill.sh` | **2 PASS / 0 FAIL**：实例被 kill 后另一实例接管，状态、分数与冻结报告全部一致（kill→恢复 **1479 ms**，请求重放幂等）；共享限流在击杀后仍是一个桶（`scope=shared`）。前置坑：沙箱 buildx 写拒绝 → 提权；构建容器连不上 pypi → 按 HANDOFF §4 带 `HTTPS_PROXY` |
| 真模型路径（真 key） | **未跑**（拍板不补 usage、维持现状；花钱链路留给你想跑时跑） |

浏览器手测只剩渲染/真模型半边：`docs/MANUAL-TESTING.md` §1.5 第 9–13 项（下拉控件、预览卡片降级提示、报告页按类一节、逐题回放对照、题目整体偏项目）。

<details><summary>原待跑清单（已执行，留档）</summary>

```bash
# （已按此执行，见上表）
# 1) 起 smoke 栈并种 smoke-fake 模型行（跑完栈保持）
bash scripts/compose_smoke.sh

# 2) 黄金路径 + 降级 + 回退全场景（证据自动落 var/evidence/<ts>-e2e/）
bash scripts/verify.sh --layer e2e
#    预期：exit 0；四个 scenario 头逐个 PASS；出现若干行 retry … HTTP 429（限流桶正常退避）；
#    DB 检查两行 PASS（或无 docker 探针时显式 SKIPPED）

# 3) 红演示（断言真的判退出码）
cd apps/api && uv run python scripts/interview_smoke.py --model smoke-fake --assert --expect-questions 4; echo EXIT=$?
#    预期：FAIL questions: contract count: expected 4, got 5 + 原始响应 + inspect 行；EXIT=1

# 4) 查库核对（脚本会打印 run_user）
docker compose exec -T postgres psql -U better_resume -d better_resume -v ON_ERROR_STOP=1 \
  -c "SELECT question_count, degraded_reasons, resume_warnings FROM interview_sessions WHERE user_id = '<run_user>' ORDER BY created_at;"
#    预期 4 行：[] / ["resume_unparsable"] / ["corpus_no_match"]+warnings / []，question_count 全 5

# 5) 真模型路径（真 key；打印报告）
cd apps/api && uv run python scripts/interview_smoke.py; echo EXIT=$?

# 6) 回归底线：部署面不得变红
bash scripts/compose_smoke.sh && bash scripts/kill_instance_drill.sh

# 7) 收尾
docker compose --profile smoke down -v
```

浏览器手测只剩渲染/真模型半边：`docs/MANUAL-TESTING.md` §1.5 第 9–13 项（下拉控件、预览卡片降级提示、报告页按类一节、逐题回放对照、题目整体偏项目）。

</details>

## 8. 用户拍板结果（2026-10-12，「同意推荐的方案」）

| # | 事项 | 决定 | 落地 |
| --- | --- | --- | --- |
| 1 | 真模型形态不在任何层 | **按推荐**：记已声明偏差；另开后续票接进 `real` 层并计入调用预算 | §5-2 定案；接层列后续票候选（本阶段不开工） |
| 2 | T4 用例写进 T2 测试文件 | **按推荐**：接受，记派工方口径扩展 | §5-6 定案 |
| 3 | e2e 每跑留行不清理 | **按推荐**：接受（唯一 run_user 隔离 + `down -v` 清库） | §5-8 定案 |
| 4 | 共享简历技能行顿号→逗号 | **按推荐**：保留并记偏差 | §5-7 定案 |
| 5 | 429 退避在真模型路径生效 | **按推荐**：保留 | §5-8 定案 |
| 6 | e2e 接进 nightly | **按推荐**：另开后续票（接在 deploy 种行之后） | 后续票候选，本阶段不开工 |
| 7 | 手测第 9 项语义标注 | **按推荐**：改标 unit 层点名用例 | `docs/MANUAL-TESTING.md` §1.5 第 9 项已改（浏览器只留下拉与「题目整体偏项目」） |
| 8 | 真模型路径补 usage 打印 | 不补（维持「与现在一致」） | 票面括注缺陷记档（PROBLEMS §1） |

其余偏差（§5-1/3/4/5）随上述拍板一并成立：票据文字缺陷与提案愿景句出入记档、不追认成规则（硬规则 3）。