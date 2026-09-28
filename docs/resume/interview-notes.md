# 面试稿：BetterResume 项目详解（不直接投递）

> **这份不是简历**，是面试准备资料：8 条长版条目 + 每个数字的出处与复跑命令，用来在面试里展开讲。
> 直接投递用的简历条目在 `docs/resume/final-resume-entry.md`（正好 5 条、每条一行）。
> 数字重取日：**2026-09-24**，基线 = `main` 干净工作区 commit `baac7e8`；每个数字的出处与复跑命令见文末《数字 → 证据》。
> 证据诚实：没跑通的（百炼应用真机）、没验的（定时排程、供应商 429 真机、浏览器矩阵）写在文末《没写进去的与未验证的》，不硬凑。

---

BetterResume—AI 模拟面试平台 https://github.com/eicon-xyz/better-resume
技术栈： Python FastAPI SQLAlchemy PostgreSQL Redis WebSocket SSE React Docker
项目简介： 一个集成用户鉴权、简历解析、AI 出题、语音/文字答题、评分追问与报告复盘的全链路模拟面试平台。针对"模型输出不可控""转写与总结长耗时阻塞面试"的痛点，把耗时任务全部异步化、模型调用统一收口，并以生产形态的故障演练与定时回归网验证可靠性。

• 用 React 19、Vite、TanStack Query、zustand 搭全栈前端，前端类型由后端 OpenAPI 生成、CI 双侧漂移检查兜底，根治前后端字段靠猜；自研 SSE 渲染器把 content、reasoning、meta、done、error 五类事件归一，打字机限速与深度思考折叠面板互不干扰；实时转写的合并语义曾散落在 store 事件、页面回调与输入框组件三层并三次复发，收敛成只替换本轮转写贡献区间的单一算法后手写内容零覆盖；部署面用 index.html 发 no-store、哈希资源发 immutable 的缓存头，根治部署后浏览器仍在跑旧 bundle；前端 175 例测试 24 个文件全绿，真实浏览器三轮手测通过。

• 用两套显式状态机重写面试会话，会话生命周期从 draft 到 finished、答题流程从 init 到 completed，状态挂在 Postgres 行上用版本号乐观锁更新，同状态幂等、非法转移显式报错，两套状态机 68 例测试穷举，解决旧项目两层状态靠约定维护的问题；追问裁决做成纯函数规则链，完成短路、追问上限、低分、要点缺失逐条判定，78 例判定表把每条分支钉死且判定链出错一律 fail-open；报告四维数字由作答分数与缺失要点纯聚合，模型只写一段总结，模型不可用也不影响报告数字。

• 用 WebSocket 一次性票据把浏览器麦克风音频实时上行，自研句池归并算法处理增量包乱序、重发与供应商整句自我纠错，端到端穿 nginx 实测开口 0.56 秒出首字、停止说话 1.1 秒拿到最终文本，顺带修掉 websockets 默认 10 秒关闭超时导致的松手 10.1 秒才出字；真机多句跑出 20 个 replace、3 个 archive 与 1 个 final，含供应商整句重写的原始帧，句池回放断言提交文本与供应商归档逐字相等。

• 用自研韧性中间件把四条 AI 链路收口到一个方法，按固定顺序串起进程内单飞、按场景熔断、舱壁、超时与令牌桶限流，74 例测试全部跑在注入时钟上、0.11 秒跑完，解决 AI 调用散落在业务代码里一处抖动全链雪崩的问题；真机把流式对话推到 24 并发，48 次请求全部成功、供应商零 429 与零 5xx，据此把单身份限流桶从 6 rps 标定到 2 rps，标定后复测 16 并发正好 8 次成功 8 次被限流，与模型分毫不差。

• 用 Redis 实现跨实例单飞与题级锁，SET NX 抢 owner、租约续租、fencing 拒写，抢锁前先查一次结果，堵住 owner 释放瞬间第二个实例插手重跑的缝隙，两实例并发提交同一道题上游只被调用 1 次；会话热态快照带来源标记、写路径主动失效，Postgres 保持唯一真相，kill 掉正在服务的实例后由另一实例接管，题号、已答数、分数与冻结报告逐字段相等；后台 worker 走 Redis Stream 消费组，带幂等键、重试退避、死信与崩溃接管，消费者拿着任务死掉后任务在 59.3 秒被接管并写完，这个数字约等于接管阈值本身，不美化。

• 用一套 10 条供应商无关契约驱动三个 LlmGateway 实现，OpenAI 兼容 adapter 吃 DeepSeek 与百炼，星云工作流 adapter 对应云端持有 prompt 的托管编排，百炼应用 adapter 对应 app_id 形态的第三个平台，30 例契约测试加突变校验证明套件有鉴别力；场景绑定存 DB 行并支持运行时切换，换供应商业务代码零改动、两个副本 0.9 秒内收敛；百炼应用真机 6 次调用被供应商判 AppId 无效，这轮没跑通的真机反而抓出带内错误帧被读成空答案的真 bug，红绿修掉后补上 3 条带内错误用例。

• 用冷卷复跑替代本机热卷自证，定位到三个演练脚本先 seed 后 migrate、定时回归网从第一次运行起就没绿过的根因，nightly 定时任务连红六晚后第一次在 CI 上真跑绿，6 分 43 秒走完部署冒烟、kill 演练与故障实验，weekly 也首次跑满 1 小时 23 分全绿；同一条链上再修三处探针缺陷与 60 分钟浸泡的证据落盘路径，浸泡跑满 3600 秒、错误率 0.0 后不再崩在写文件上；另修掉一个拿对象内存地址当资源名、导致相邻用例互相偷任务的偶发失败，脚本回归契约从 27 例涨到 44 例。

• 用生产形态故障演练代替方案评审验收容错，脚本化执行 kill 实例、Redis 网络分区、主从切换与 60 分钟浸泡，恢复动作一律放 finally，任何崩溃都不会把栈留在故障态；分区期间健康检查 9 次全过、认证路径按 503 加 Retry-After 降级而不是假装未登录、恢复 0.2 到 2.2 秒；主从切换 92 次请求 91 次成功、恢复 109 毫秒、切换前会话存活，并揪出心跳写在兜底 try 之外、主从切换时 worker 直接退出 1 的真 bug；60 分钟浸泡 3600 次请求零失败，非会话 Redis 键零增长、Postgres 连接零增长、进程内存每小时增长 0.5 MB。

---

## 数字 → 证据

> 口径：本机数字一律是 2026-09-24 在 `main` 干净工作区 commit `baac7e8` 上实测；CI 数字是 GitHub Actions 的真实 run。
> 复跑前先 `export PATH="$HOME/.local/bin:$PATH"`、`export UV_CACHE_DIR='/root/better resume/.cache/uv'`。

### 测试基线

| 数字 | 出处 | 复跑 |
| --- | --- | --- |
| 后端 **800 passed / 0 failed / 0 skipped** | 本次实测（junitxml 实读，2026-09-24 06:53 UTC；旧稿 747 已过期） | `cd apps/api && export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0' && uv run pytest --junitxml=/tmp/x.xml` |
| 前端 **175 passed / 24 files** | 本次实测（同一工作区） | `pnpm -C apps/web test --run` |
| 状态机 **68 例** = 会话 38 + 流程 30 | 本次实测 `tests/interview_engine/test_session_fsm.py`、`test_flow_fsm.py` | `uv run pytest tests/interview_engine/test_session_fsm.py tests/interview_engine/test_flow_fsm.py --collect-only -q` |
| 追问裁决 **78 例判定表** | 本次实测 `tests/interview_engine/test_follow_up.py` | `uv run pytest tests/interview_engine/test_follow_up.py --collect-only -q` |
| 韧性 **74 例 / 0.11 秒** | 本次实测 `tests/ai_resilience` | `uv run pytest tests/ai_resilience` |
| 契约 **10 条 × 3 实现 = 30 例** | `tests/llm_gateway/test_adapter_contract.py`；M5 提案与 `p3-dashscope-app/README.md` §9 | `uv run pytest tests/llm_gateway/test_adapter_contract.py --collect-only -q` |
| 句池归并 **22 例** | `docs/resume/M4-resume-draft.md` §2；`tests/media/test_assembler.py` | `uv run pytest tests/media/test_assembler.py --collect-only -q` |
| 前端雷达几何 **11 例** | `apps/web/src/interview/radar.test.ts` | `pnpm -C apps/web test --run src/interview/radar.test.ts` |

### 前端链路

| 数字 | 出处 | 复跑 |
| --- | --- | --- |
| 实时转写三层合并、三次复发 | `docs/tickets/p1-post-v/PROBLEMS.md` P28 / P30；代码里 `replaceTranscript` 三个调用点：`pages/InterviewRoomPage.tsx`、`pages/ChatPage.tsx`、`pages/chat/Composer.tsx` | `grep -rn "replaceTranscript" apps/web/src` |
| index.html no-store、/assets/ immutable | `scripts/compose_smoke.sh` 第 92–97 行两条断言；P29 台账 | `bash scripts/compose_smoke.sh`；或 `curl -sI http://127.0.0.1:8080/ \| grep -i cache-control` |
| 五类 SSE 事件 content / reasoning / meta / done / error | `apps/web/src/stream/renderer.ts`、`apps/web/src/api/sse.ts`；`docs/resume/M1-resume-draft.md` | `pnpm -C apps/web test --run src/api/sse.test.ts src/stream/renderer.test.ts` |
| OpenAPI → TS 类型生成 + 双侧漂移检查 | 决议 D17；`apps/web/package.json` 的 `gen:api` / `check:api` | `cd apps/api && uv run python scripts/export_openapi.py --check && pnpm -C apps/web check:api` |
| 真实浏览器三轮手测通过 | `docs/tickets/p1-post-v/ACCEPTANCE.md` §7；`docs/MANUAL-TESTING.md` §5 | 人工清单 |

### 语音与实时转写

| 数字 | 出处 | 复跑 |
| --- | --- | --- |
| 首增量 **0.56 s**、松手→final **1.1 s**、关闭码 **1000** | `docs/tickets/p1-post-v/P1-A-EVIDENCE.md` §3c | `uv run python scripts/v3_ws_probe.py --realtime`（需栈在跑，1 次真调用） |
| 修复前松手→final **10.1 s**，根因 websockets 默认 close_timeout=10s | `P1-A-EVIDENCE.md` §3d；台账 P24（`p1-post-v/ACCEPTANCE.md` §2） | 同上（修复前后对照留档在 §3d） |
| 真机多句 **20 replace + 3 archive + final 1**，含供应商整句自我纠错 | `docs/tickets/p1-post-v/P1-C-EVIDENCE.md` §2 | `uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav` |
| 句池提交语义 **PASS**（提交文本 == 供应商归档），已知边界 26 段 vs 3 句 | `P1-C-EVIDENCE.md` §3 | `uv run python scripts/assembler_real_probe.py` |

### 韧性 / 分布式 / 多平台

| 数字 | 出处 | 复跑 |
| --- | --- | --- |
| 真机 **24 并发、48/48 全 ok、0 供应商 429/5xx** | `docs/tickets/p1-post-v/P1-B-EVIDENCE.md` §1 阶段 2 | `uv run python scripts/load_test.py --scenario chat-sse --concurrency 16 --requests 16`（真调用，注意花费） |
| 限流桶标定 **ai_call 6→2、answer 8→2**；标定后 c=16 → 8 ok + 8 rate_limited | `P1-B-EVIDENCE.md` §2 | `uv run pytest tests/ai_resilience/test_ratelimit.py -k calibrated` |
| 两实例并发同 key **上游只调用 1 次**；题级锁 10 例、单飞 10 例 | `docs/tickets/m6/ACCEPTANCE.md` §2；`tests/test_distributed_flight.py`、`test_distributed_lock.py` | `uv run pytest tests/test_distributed_flight.py tests/test_distributed_lock.py` |
| kill 实例 → 另一实例接管、状态/分数/冻结报告逐字段相等 | `m6/ACCEPTANCE.md` §1（kill→recovery 1304 ms）；冷卷复跑 260 ms 见 `p4-nightly-green/ACCEPTANCE.md` §2.3 | `bash scripts/kill_instance_drill.sh` |
| worker 崩溃后任务 **59.3 s** 被 XPENDING+XCLAIM 接管并完成 | `docs/tickets/v1-verification/V6-EVIDENCE.md` §3 | `bash scripts/fault_injection_drill.sh --quick` |
| 场景绑定 PUT 后两副本 **0.9 s** 收敛；换供应商业务代码零改动 | `docs/tickets/v1-verification/ACCEPTANCE.md` §1（V4） | `uv run pytest tests/llm_gateway/test_scene_binding_propagation.py` |
| 百炼应用真机 **6 次调用全部被拒**（InvalidParameter: AppId） | `docs/tickets/p3-dashscope-app/EVIDENCE.md` §1、§4 | `uv run python scripts/dashscope_app_probe.py --dry-run`（dry-run 不花钱） |
| 带内错误帧被读成空答案的真 bug（P34）+ 3 条新用例 | `p3-dashscope-app/EVIDENCE.md` §2；`PROBLEMS.md` | `uv run pytest tests/llm_gateway/test_dashscope_app_adapter.py` |

### 守护网与故障演练

| 数字 | 出处 | 复跑 |
| --- | --- | --- |
| nightly 定时任务 **连红六晚**，每次 24–31 秒即挂 | runs `35319873282` `35429374534` `35497979631` `35576171196` `35701690467` `35834069963`（09-18 ~ 09-23，全部 schedule on main） | `gh run list --workflow nightly --limit 12` |
| nightly 真跑绿 run **35835316554**（success，6 分 43 秒，workflow_dispatch） | `p4-nightly-green/ACCEPTANCE.md` §4 | `gh run view 35835316554` |
| weekly-full 修 P39 前 `35836425404` failure（60 分钟浸泡 `error_rate 0.0` 却崩在写证据） → 修后 `35870043832` success（1 小时 23 分） | `p4-nightly-green/ACCEPTANCE.md` §4；`PROBLEMS.md` P39 | `gh run view 35870043832` |
| 三个脚本先 seed 后 migrate 的根因 + 冷卷红绿 | `p4-nightly-green/README.md` §1；`ACCEPTANCE.md` §2.1–2.4 | `docker compose --profile smoke down -v && bash scripts/compose_smoke.sh` |
| `verify.sh --layer all` **12 条命令全绿** | `p4-nightly-green/ACCEPTANCE.md` §2.5 | `bash scripts/verify.sh --layer all` |
| 脚本回归 **27 → 44 例** | `p4-nightly-green/ACCEPTANCE.md` §3、§6 | `uv run pytest tests/test_drill_prereqs.py tests/test_fault_probe.py --collect-only -q` |
| 拿 `id()` 当资源名的偶发失败：12 个 Settings 只产出 2 个不同地址 | `apps/api/tests/test_job_worker_api.py` 的 `_private_jobs_stream()` docstring 与 `test_private_jobs_stream_is_unique_per_call` | `uv run pytest tests/test_job_worker_api.py -k private_jobs_stream` |
| 网络分区：healthz **9/9**、认证 503 + Retry-After、恢复 207 ms / 2200 ms | `docs/tickets/p1-post-v/P1-D-EVIDENCE.md` §2 | `uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20` |
| 主从切换 **91/92 ok、恢复 109 ms**、会话存活、worker 存活 | `P1-D-EVIDENCE.md` §3 | `uv run python -m scripts.fault_probe fault --scenario redis-failover --seconds 20` |
| worker 心跳写在兜底 try 之外导致 exit 1 的真 bug（P26） | `P1-D-EVIDENCE.md` §4 | `uv run pytest tests/test_worker_health.py tests/test_worker_loop.py` |
| 60 分钟浸泡 **120 波 / 3600 请求 / 0 失败**，非会话键 +0、PG 连接 +0、内存 +0.5 MB/h | `P1-D-EVIDENCE.md` §5 | `bash scripts/fault_injection_drill.sh`（含浸泡） |

---

## 没写进去的与未验证的

**没进 bullet 的**，因为全栈定位下条数给了前端与守护网：

- TTS 题目播报：edge-tts 真合成 25.2 KB mp3 + 内容寻址缓存 + 单例播放器（`docs/resume/M4-resume-draft.md` §1）。
- skills 知识库：repo-map + 10 份模块 SKILL.md + 脚本生成的 API 索引 24 条 REST、1 条 WS，39 例漂移检查（`m6/ACCEPTANCE.md` §4）。
- M0 工程地基与 CI 双 job：`docs/resume/M0-resume-draft.md`（属过程记录，不作亮点）。

**没验的，如实标注**：

1. **定时排程本身仍无绿灯记录**：P4 验收时写「nightly 首次自然排程 = 2026-09-24 02:30 UTC」，但截至 2026-09-24 06:59 UTC，`gh run list --workflow nightly` 里**没有** 09-24 那次定时运行；已绿的两次都是 workflow_dispatch 手工触发。weekly 的下一次自然排程 = 周日 03:00 UTC，同样未验。
2. **百炼应用链路真机未成功**：给定 app_id 被判 `AppId missing or invalid`，需要账号侧确认应用是否已发布；结构化输出边界、增量时序、usage、session_id 多轮均未测（`p3-dashscope-app/EVIDENCE.md` §4）。
3. **讯飞 AST / 星云工作流原生 adapter 真机**：无凭据，一直未验证（用阿里同类能力覆盖，非同一协议）。
4. **供应商 429 真机表现**：177 + 6 次真调用一次未触发，退避/重试路径仍是纸面推演。
5. **>24 并发、>60 分钟长跑、多可用区、浏览器矩阵**：未测。
6. **自动 failover 尚未落地**：应用仍是单 `BR_REDIS_URL`，本文写的恢复时间都是**人工切换**的停机时间；自动切换是另一张提案（P5）。

**与旧稿的差异**：删除旧稿的 **747 / 173**（过期，重取为 800 / 175）；新增 P3、P4、P39、P40 与前端独立条目；旧稿 7 条 bullet 里能查到出处的数字原样保留，查不到出处的已删。

---

## 备选条目（按岗位取舍）

> 简历只有 5 条，以下三条是被挤掉的候选，按目标岗位替换任意一条即可（同样是「用什么技术，解决了什么问题，有数据摆数据」句式）。

- 采用一套 10 条供应商无关契约驱动 3 个 LlmGateway 实现，解决换供应商要改业务代码的问题，换绑后两个副本 0.9 秒内收敛。
- 用冷卷复跑定位三个演练脚本先 seed 后 migrate 的根因，解决定时回归网从第一次运行起就没绿过的问题，nightly 连红六晚后 CI 真跑绿、weekly 首次跑满全绿。
- 用脚本化故障演练代替方案评审验收容错，执行 kill 实例、Redis 分区、主从切换与 60 分钟浸泡，解决高可用只停留在纸面的问题，3600 请求零失败。
