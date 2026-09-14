# P2 提案：测试自动化方案（分层 · 单一入口 · 可调度的重型验证）

> 依据：`AGENTS.md`（契约三件套、本地必须镜像 CI）、M6 P16（"本地全绿、CI 直接红"）、
> P25/P27（证据工具自身要先被校准）、P1 收口时的实测盘点。
> 状态：**提案，待你确认后动工**（本文件只出方案，未改任何代码/流程）。

## 1. 现状盘点（实测，不是印象）

| 层 | 内容 | 现在在哪跑 | 触发方式 | 缺口 |
| --- | --- | --- | --- | --- |
| **L0 单元/组件** | pytest **695** + vitest **161** | CI 双 job | push / PR | 无覆盖率度量 |
| **L1 契约/进程内集成** | 假上游（`fake_openai`）、假 WS 服务端、TestClient、契约三件套的 `--check`（openapi / api-index / gen:api） | CI | push / PR | 契约命令散落在 README/票据/CI 三处，本地靠"记得跑" |
| **L2 部署面** | `compose_smoke.sh`、`kill_instance_drill.sh` | **手工**（本机 docker） | 想起来才跑 | 无自动触发；输出不留档 |
| **L3 故障/浸泡** | `fault_injection_drill.sh`（5 实验 + 2/20 分钟浸泡）、`redis-partition`、`redis-failover`、60 分钟浸泡 | **手工** | 阶段收口时 | 同上；**回归无人守护**（P26 就是这么被手工演练抓到的） |
| **L4 真机** | `real_model_smoke`、`media_smoke`（真 ASR）、`v3_ws_probe`、`assembler_real_probe`、`load_test`（真模型） | **手工** | 阶段收口时 | 花费无守卫；**样本音频未入库**（`data/audio/` 未跟踪 → 别人复跑不了） |
| **L5 脚本自身回归** | 脚本 3437 行 Python + 296 行 shell；**只有 3 个脚本有测试**（`test_fault_probe` / `test_load_test_script` / `test_real_model_smoke_script`） | CI（那 3 个） | push / PR | 11 个脚本零测试（P1 新增的 `media_smoke` / `assembler_real_probe` / `v3_ws_probe` 都在其中） |

CI 现状（`.github/workflows/ci.yml`）：仅 push/PR 触发；无 `schedule`；无 artifacts 上传；无覆盖率。

## 2. 目标（可验收的成功标准）

1. **一套入口**：`scripts/verify.sh --layer unit|contract|deploy|fault|real|all`，**本地与 CI 调用同一份命令**
   （从根因上消灭"本地绿、CI 红"）。
2. **能自动跑的重型层真的自动跑**：deploy / fault 进 nightly；浸泡进 weekly；**真机层永不进 CI**（凭据 + 花费）。
3. **真机层有预算守卫**：调用计数 + 封顶，超限即停并落证据；缺凭据时**明确失败**而不是静默跳过。
4. **证据留档**：每次运行的 junit / 日志 / JSON 收进 `var/evidence/<timestamp>/`；CI 上传 artifacts。
5. **脚本自身有回归**：每个脚本至少两条契约——纯逻辑、以及"无 docker/无凭据时必须拒绝假装跑过"。
6. **覆盖率可见**：先度量、后设闸；只给深模块设 per-module 底线，不追全局百分比。
7. **flake 诚实**：不自动重试掩盖、不静默 quarantine；不稳定就是缺陷。

## 3. 分层设计

| 层 | 命令（单一事实源） | 在哪跑 | 触发 | 时长预算 |
| --- | --- | --- | --- | --- |
| L0 | `verify.sh --layer unit` → `pytest -m "not docker and not real"` + `vitest run` | 本机 / CI | push、PR | ≤ 3 min |
| L1 | `verify.sh --layer contract` → ruff check/format、eslint、tsc、alembic check、契约三件套 `--check` | 本机 / CI | push、PR | ≤ 4 min |
| L2 | `verify.sh --layer deploy` → compose_smoke + kill_instance_drill | CI（nightly）/ 本机 | schedule、手动 | ≤ 12 min |
| L3 | `verify.sh --layer fault` → 5 个故障实验 + partition/failover + 20 min 浸泡 | CI（nightly）/ 本机 | schedule、手动 | ≤ 35 min |
| L3b | `verify.sh --layer soak` → 60 min 浸泡（**零供应商调用**） | CI（weekly）/ 本机 | schedule、手动 | 60 min |
| L4 | `verify.sh --layer real` → 真机套件 + 预算守卫（读 `.env` 的 `BR_REAL_CALL_BUDGET`，默认 200） | **本机 only** | 手动、阶段收口清单 | 花费封顶 |
| L5 | `verify.sh --layer scripts` → 脚本回归测试 | 本机 / CI | push、PR | ≤ 1 min |

## 4. 票据拆分

| 票 | 标题 | 交付物 | 测试 / 验收 | 预估 |
| --- | --- | --- | --- | --- |
| **T1** | `scripts/verify.sh` 单一入口 | 分层入口脚本 + 证据目录约定 + CI 两个 job 改调它 | 同一命令本机与 CI 各跑一次，产物结构一致；`--list` 可打印层命令 | 0.5 会话 |
| **T2** | pytest markers 分层 | `unit` / `docker` / `real` 标记 + `--strict-markers` + 默认排除重型 | 误用标记会失败；`-m` 选择生效 | 0.3 会话 |
| **T3** | nightly / weekly workflow | `schedule`（频率按 §7 选定 A/B/C）+ `workflow_dispatch` + artifacts 上传 + 失败摘要 | 手动 dispatch 跑通一次并下载到产物 | 0.5 会话 |
| **T4** | 真机套件 + 预算守卫 + 音频生成器 | `verify.sh --layer real` + 调用计数 + 证据落盘 + 缺凭据即失败；`scripts/make_fixture_audio.py`（TTS 合成 → 16k wav + **sha256 校验**，不把 wav 入库） | 计数器与真机日志一致；超预算非零退出；校验和不匹配即失败 | 0.7 会话 |
| **T5** | 脚本回归补齐（12 个，含新生成器） | 每个脚本 ≥2 条契约测试（纯逻辑 + 拒绝假装） | 脚本层覆盖率 3/14 → 全覆盖 | 1.0 会话 |
| **T6** | 覆盖率度量（两轮） | 第一轮：pytest-cov + vitest `--coverage` 只出报告；第二轮：按 §5.5 清单给**深模块**设底线（浅模块不设数字） | 报告在证据目录；底线只落在深模块且改动需在票据里说明理由 | 0.5 会话 |

**依赖**：T2 先于 T1/T5；T1 先于 T3/T4；T6 独立。

## 5. 关键设计决策（取舍，需你点头）

- **D1 单一入口优先于"CI 里再抄一遍命令"**：verify.sh 是唯一事实源，CI 只调用它——这是 M6 P16 的根治。
- **D2 重型层放 GitHub Actions nightly**：ubuntu runner 自带 docker，L2/L3 可跑；**私有仓库会消耗 Actions 分钟数**（见 Q1）。
- **D3 真机层永不进 CI**：凭据只在本机 `.env`；改为"阶段收口必跑清单 + 预算守卫"。
- **D4 不自动重试**：flake 必须被修或被显式标注，不允许 retry 掩盖。
- **D5 样本音频**：入库（约 400 KB × 2）或改成"脚本生成 + sha256 校验"（见 Q3）。
- **D6 覆盖率只设深模块底线**（`ai_resilience` / `interview_engine` / `media` / `identity` / `jobs`），不设全局百分比——避免为数字写垃圾测试。

## 5.5 覆盖率与深模块口径（Q4 落地 —— 用 codebase-design 的词汇）

**判据（你的要求，翻译成可操作的规则）**：*深模块 = 小接口 + 厚实现*；**深度是接口的属性**。
一个模块值得设覆盖率底线，当且仅当：

1. **通过删除测试**：把它删掉，复杂度会在 N 个调用点重新出现（不是一层透传）；
2. **接口面小而稳**：公开方法少、参数简单（本仓库举例：`ResilientAiResilience.run(stage, key, fn)`、
   `TranscriptionChannel.start/feed/stop/wait`、`JobQueue.claim/ack/fail/reclaim_stale`）；
3. **实现厚**：状态机 / 并发 / 重试 / 合并算法这类复杂度集中在它内部。

**测试口径三分法（顺序即优先级）**：

| 优先级 | 测什么 | 跨哪个缝 | 例子 |
| --- | --- | --- | --- |
| ① 接口测试（行为） | 调用者能观察到的行为 | **与调用者同一个缝** | 通道事件序列 `replace/archive/final`、限流判定、报告冻结幂等 |
| ② 内部缝测试 | 实现内部的私有缝（只在该复杂度确实需要时） | 模块内部 | 句池合并的纯函数、重试退避策略 |
| ③ 覆盖率底线 | **实现层**的复杂分支有没有人走过 | 不是缝，是度量 | 只对下面清单里的深模块设数字 |

**关键立场**：覆盖率是**实现层的代理指标**——它不衡量设计好坏，只回答"厚实现里有没有没人走过的复杂分支"；
"想要测到接口之外"本身就是模块形状不对的信号（应改接口，而不是加白盒测试）。
因此：**深模块设底线，浅模块不设数字**，只做缝上的契约测试。

**本仓库的深模块清单（设底线）与其接口**：

| 深模块 | 小接口 | 实现里的复杂度 |
| --- | --- | --- |
| `ai_resilience` | `run(stage, key, fn)` / `StagePolicy` | 单飞 / 熔断 / 舱壁 / 超时 / 限流 / 分布式单飞 |
| `interview_engine` | 锁、热层、报告服务各一小组方法 | 题级锁、热层失效、报告冻结幂等 |
| `media` | `TranscriptionChannel`(4 方法)、`AstTranscriptionAssembler.apply(packet)` | 四家供应商协议、句池归并、尾部预算 |
| `identity` | `SessionStore`(get/create/touch/delete) + ticket | 滑动过期、并发续期、后端降级语义 |
| `jobs` | `JobQueue`(claim/ack/fail/reclaim) + `serve` | 心跳、重试、死信、崩溃接管 |
| `llm_gateway` | `resolve(scene)` + adapter `complete/stream` | 场景绑定 TTL、schema 校验重试、usage 请求 |
| `resume_parser` | `parse(bytes) → ResumeContext` | 章节启发式打分、CJK 回退 |

**浅模块（明确不设数字，只做缝契约）**：`media/adapters/*` 里的薄适配器、`media/factory`、
`settings/config`、`observability`、`http/*` 路由壳。

**接口间的关系怎么测**（你说的"接口间的关系"）：用**缝上的集成测试**断言链路行为，而不是内部状态——
`resolver → adapter → resilience → endpoint`、`channel → WS endpoint → 前端 store`、
`answer 提交 → 题级锁 → 单飞 → worker`。这套已经在跑（假供应商 / 假 WS / TestClient），本方案只是把它固化成层。

## 6. 不做

- 不引第三方测试平台（Codecov / Allure / SonarQube）、不做 mutation testing；
- 不做浏览器矩阵自动化（Playwright 若要，另开提案——P1 的浏览器手测仍归人工）；
- 不把真机/浸泡放进 PR 门禁（PR 必须快）；
- 不做 CI 缓存调优（沿用现有 uv / pnpm 缓存）；
- 不为覆盖率补无意义断言。

## 7. 你的决定（已收到）与最后一项待选

| # | 你的决定 | 对方案的影响 |
| --- | --- | --- |
| Q1 | **公有仓库**（实测 `gh repo view`：`visibility: PUBLIC`，2026-09-15 确认） | **标准 runner 对公共仓库免费**，分钟数不再是约束 → 采用**方案 A**（每天 nightly + 每周全量 + 60 分钟浸泡）；仍不做无意义的超长任务 |
| — | **公开前的凭据预检（已做，结论：干净）** | `.env` 从未提交（仅 `.env.example`）；三个 key 的值在**全部历史**里 0 命中；无 `sk-*`/Bearer 模式；`data/` 与 `.env` 未跟踪（2 MB / 505 文件）。注意：ASR 样本转写文本含人名与学校（用户本人录音），已在公开历史中 |
| Q3 | **脚本生成音频**（不把 wav 入库） | T4/T5 增加 `scripts/make_fixture_audio.py`（TTS 合成 + 16k 转码）+ 固定 sha256 校验；探针启动时校验，不匹配即失败 |
| Q4 | **先报告、再设深模块底线** | 见 §5.5；T6 = 先出报告，第二轮才落深模块底线 |
| Q5 | **强制** | 真机套件是"阶段收口必跑清单"的必选项；超预算/缺凭据 → **非零退出**，不接受静默跳过 |

### Q2：60 分钟浸泡 —— "weekly 定时"与"只手动"的实际区别

| 维度 | weekly 定时（CI） | 只手动 |
| --- | --- | --- |
| 抓慢漂移（泄漏、键累积、TTL 错） | 自动，最迟一周暴露 | 只在你想起来时暴露；两次之间静默 |
| 成本 | 约 **70 分钟/次 ≈ 300 分钟/月** | 0 |
| 运行环境 | GitHub runner（**不是你的机器**）→ 能发现"换机就跑不起来" | 你的本机（真实开发环境） |
| 证据 | 自动留档 + artifacts，历史可追 | 只有终端输出，除非手工保存 |
| 对 PR 门禁的影响 | 无（不进 PR） | 无 |

**Actions 分钟预算**：公共仓库的标准 runner **免费**（本仓库已确认 PUBLIC），所以按**方案 A** 执行：

| 方案 | nightly（L2 + L3-quick） | weekly（完整 L3 + 60 min 浸泡） | 结论 |
| --- | --- | --- | --- |
| **A（采用）** | 每天约 20 min | 每周约 90 min | 覆盖最密；分钟免费，无成本顾虑 |
| ~~B 一三五~~ / ~~C 只 weekly~~ | — | — | 私有仓库时代的备选，现已不需要 |

即便免费也守住两条纪律：**≤1 小时的 job 超时**、**失败即失败不重试**（免费不等于可以掩盖 flake）。

（Q2 因此自动落定：weekly 跑 60 分钟浸泡；环境差异与证据留档的价值现在没有成本对手。）

## 8. 验收口径（方案本身的）

1. `scripts/verify.sh --layer all` 在本机一次跑通，且**每一层都产出结构一致的证据**（junit + 日志 + JSON）；
2. CI 的 nightly 手动 dispatch 跑通一次并可从 artifacts 下载证据；
3. 真机套件在预算内跑完；**超预算或缺凭据时明确失败**（不是静默跳过）——Q5 已定为**强制**：它是阶段收口清单的必选项；
4. 样本音频可**从零重建**：`make_fixture_audio.py` 生成的文件 sha256 与记录一致；
5. 脚本层测试从 3/14 提升到全覆盖（每个脚本至少两条契约）；
6. 覆盖率第一轮只出报告；第二轮深模块底线落地（浅模块不设数字，理由写进票据）；
7. 连续 3 次 nightly 全绿；若失败，证据里能直接看到是哪一层、哪条命令、原始输出。

## 9. 预估

T1–T6 合计 **约 3–3.5 个会话**；其中 T3（云上定时）需要你先回答 Q1。
