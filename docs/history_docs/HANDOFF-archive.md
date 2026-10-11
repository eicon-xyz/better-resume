# 历史归档：阶段流水与经验教训

> **这是历史记录，不是当前状态。** 当前状态看 docs/HANDOFF.md；阶段票据与验收包在 docs/history_docs/tickets/。
> 本文件保留已完成阶段的推进流水、逐票状态与当时总结的经验教训——供回溯某个决定当初为什么这么定。

## 阶段状态流水（原 HANDOFF 1）

## 1. 一句话状态

**M0–M6、V、P1–P6 已全部合并进 main**（P5 = PR #15、P6 = PR #16，均 2026-09-28 合并）。
**P4 守护网修复**（P35–P38、P39、P40）让 `nightly` 与 `weekly-full` 从「上线起从没绿过」变成**真跑绿**
（nightly `35835316554`、weekly `35870043832`）。真机花费 ~191 次（P1 约定 200 封顶内；`verify.sh --layer real` 自带预算守卫）。

**P7（限流状态迁到 Redis）已合并**——**PR #18**（`p7/stage-close` → `main`，merge `15f073e`，2026-10-07）：**N 个副本共享同一份对外配额**
（只共享供应商成本桶 `ai_call/answer/heavy`；`general/read` 限的是自己的容量，按副本限才是对的），Redis 不可用时
**降级回进程内桶**并把降级做成可观测量（`rate_limit_degraded` 计数 + 响应头 `X-RateLimit-Scope: shared|instance` + 30s 冷却）。
验收数字（`docs/tickets/p7-shared-rate-limit/ACCEPTANCE.md`）：后端 **842 passed**、`bash scripts/verify.sh --layer all` =
**ALL PASS（12 条命令）**；真机调用 **0 次**。决议 = **D19**。

**审计/文档线已合并**——**PR #19**（`audit/gates-and-glossary` → `main`，merge `f915f20`，2026-10-07）：模块设计审计（122 条问题，`docs/audit/`）
+ ai-02 修复 + 验证工具链（`verify_mutation.sh` / `check_scripts.py` / 引证两级核对）+ `GLOSSARY.md` + 决议 D20/D21/D22。

**当前 `main` = `d1b764c`（CI 绿）**，没有挂起的 PR。**在飞（未推送、待用户验收）**：`p8/audit-hardening`（审计高危项硬化：
5 修复 + 3 守卫；验收包 `docs/tickets/p8-audit-hardening/ACCEPTANCE.md`；实测后端 879 / 前端 177 / `verify.sh --layer all` ALL PASS）与
`docs/agents-md-drift`（只改本文与 `AGENTS.md` 的文档漂移）。下一次开工要么开新阶段提案，要么从 `docs/audit/FIXES.md` 台账里挑一条。

> **教训（PR #17 踩的）**：把 PR 的 base 选在阶段分支，合并只会落在阶段分支上（#17 因此只进了 `p7/shared-rate-limit`，
> 直到 #19 才真正进 main）。阶段分支只用来收口一个阶段；跨阶段的内容直接对 `main` 开 PR。

## V 阶段逐票状态（原 6）

## 6. V 阶段逐票状态（证据入口）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| V1 真模型四链路 + 失败面 | ✅ | DeepSeek 真机：四链路 + 缺凭据 503 点名变量 | `V1-EVIDENCE.md`；`uv run python -m scripts.real_model_smoke --failure-probe` |
| V2 真模型容量 + 拐点 | ✅ | chat p50 1.9s（我们增量 ~30ms）；限流钉住 ~23 ok/s，c=80 拒绝路径 p50 134ms | `V2-EVIDENCE.md` + `docs/perf/M6-capacity.md` §2.4–2.6 |
| V3 语音识别真机 | ✅ | 百炼 Qwen-Audio-ASR-Flash（**批量**）：5.5s 音频 1.15s 出文本；WS 端到端 0.77s 收 final、干净关闭 1000 | `V3-EVIDENCE.md`；`media_smoke.py --qwen-asr-real --wav data/audio/v3-sample-16k.wav`；`scripts/v3_ws_probe.py` |
| V4 第二家 LLM 平台 | ✅ | 百炼 qwen-plus **零代码**接入，四链路 + 与 DeepSeek 对照 + P18 多副本复证 | `V4-EVIDENCE.md` |
| V5 浏览器人工手测 | ✅ | 用户本机 Chrome：两次不同句子**追加**显示、手写内容未被覆盖、TTS 正常 | `V5-EVIDENCE.md` |
| V6 浸泡 + 故障注入 | ✅ | redis-pause/restart 语义；worker 崩溃任务 59.3s 被接管；10 分钟 600 请求 0 失败 | `V6-EVIDENCE.md`；`bash scripts/fault_injection_drill.sh [--quick]` |

阶段问题台账：`docs/tickets/v1-verification/PROBLEMS.md`（P17–P21）。

## P1 阶段逐票状态（原 6b）

## 6b. P1 阶段逐票状态（证据入口）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| P1-A 实时 ASR | ✅ 手测通过，待正式验收 | 百炼 Paraformer 实时：端到端首增量 **0.56s**、松手→final **1.1s**（修 P24 前 10.1s）；句池不被该供应商触发（直连 replace/archive） | `P1-A-EVIDENCE.md`；`scripts/v3_ws_probe.py --realtime` |
| P1-B 真模型容量 + 限流标定 | ✅ 待验收 | 24 并发真流 0 供应商错误；标定 `ai_call 6→2`、`answer 8→2`（红-绿 + 实证） | `P1-B-EVIDENCE.md` + `docs/perf/M6-capacity.md` §2.7 |
| P1-C 阿里 API 补验 | ✅ 待验收 | 多句真机（3 句、含供应商自我纠错）；句池真机包回放提交语义 PASS + 已知边界 | `P1-C-EVIDENCE.md`；`scripts/assembler_real_probe.py` |
| P1-D 生产形态演练 | ✅ 待验收 | 分区（503+Retry-After、恢复 0.2–2.2s）/ 主从切换（恢复 109ms、worker 存活）/ 浸泡 3600 请求 0 失败 | `P1-D-EVIDENCE.md`；`fault_probe.py fault --scenario redis-partition|redis-failover` |

阶段问题台账：`docs/tickets/p1-post-v/PROBLEMS.md`（P24–P27 + 验收轮新增 P28–P30）；阶段验收包：`docs/tickets/p1-post-v/ACCEPTANCE.md`。

**P1-A 浏览器手测已完成**（第 3 轮通过，2026-09-17）：实时出字 ✅、录音中打字原位保留 ✅；过程中修掉
P28（页面级合并层）→ P29（部署缓存头）→ P30（chat Composer 内部第三层合并）——全部红-绿 + 页面级回归用例，
结论与每轮记录在 `docs/MANUAL-TESTING.md` §5。

## P2 阶段逐票状态（原 6c）

## 6c. P2 阶段逐票状态（测试自动化）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| T1 verify.sh 单一入口 | ✅（含 P31 修正） | 分层 unit/contract/coverage/deploy/fault/soak/real/scripts/all + --dry-run/--list；CI 双 job 已改调它；**all 层曾静默漏 contract**（P31，2026-09-17 修：抽 builder 复用 + 展开漂移测试） | `scripts/verify.sh`；`tests/test_verify_script.py`（钉 `all` 的展开 ⊇ 各层展开，并钉 `--list` 的地图 == 真实展开） |
| T2 pytest markers | ✅ | --strict-markers + 默认 `-m 'not docker and not real'` | `tests/test_pytest_config.py` |
| T3 nightly/weekly | ✅（首跑等合并） | 公有仓库免费：nightly=deploy+quick fault；weekly=全量故障+60min 浸泡；YAML 本地已校验；**schedule 只认默认分支**，合并后自动首跑 | `.github/workflows/nightly.yml`、`weekly-full.yml` |
| T4 真机套件+预算守卫 | ✅（含 P32 修正） | BR_REAL_CALL_BUDGET=200、超预算/缺凭据非零退出、dry-run 列清单；音频生成器钉 sha256；**fixture 预检**（P32：缺文件/字节漂移都在花钱前 exit 2，`VERIFY_FIXTURE_AUDIO_DIR` 可覆盖） | `verify.sh --layer real`；`make_fixture_audio.py --check`；`tests/test_real_layer.py` |
| T5 脚本回归 | ✅ | 14/14 脚本 ≥2 契约（import 隔离/argparse/拒绝假装/同步性） | `tests/test_scripts_contracts.py` |
| T6 覆盖率两轮 | ✅ | 报告→底线：7 深模块 ≥90% 进 CI（缺数据=违规）；浅模块不设线 | `scripts/check_coverage_floors.py`；`coverage-report-round1.md` |

## 可复用的经验教训（原 7）

## 7. 可复用的经验教训（精华）

**契约与实现**
1. 实现 Protocol ≠ 满足契约：`wait()` 该阻塞却立即返回，类型检查全绿、端到端第一帧就断（P20）。
   新 adapter 必须跑一次真实链路，不能只看单测。
2. "可选字段"最容易静默丢失：流式 `usage` 需按平台请求（P19）——没有报错，只有空值。
3. 缓存要有 TTL 或跨进程失效：多副本下"只在本地失效"= 配置漂移（P18，8 个 503 一度被误判为供应商限流）。
4. 缺配置要报"不可用"，不是"你未登录"：Redis 挂了应是 503 + Retry-After，不是 500（P17）。
5. 过期视图比慢视图更糟：热层读缓存必须写路径失效（M6 P6）。
6. 未 await 的协程恒为真值 → "检查"变"永远通过"（M6 P8）；测试里加 RuntimeWarning 断言很便宜。

**分布式与异步**
7. 先查结果再抢锁：否则 owner 释放瞬间会出现"空档重跑"（M6 P2）。
8. 队列要兼容下限版本：Redis 6.0 没有 `XAUTOCLAIM`/带 IDLE 的 `XPENDING`，且 `XCLAIM` 只返回条目列表（M6 P7）。
9. worker 不能死于依赖抖动：阻塞读被取消会包装成 TimeoutError 逃出循环（M6 P9）。
10. 崩溃恢复时间 = 接管阈值本身（实测 59.3s ≈ `min_idle_ms=60s`），不要美化。

**部署与验证**
11. compose 必须有迁移步骤（一次性 `migrate` 服务 + `service_completed_successfully`），否则新卷直接 500（M6 P10）。
12. 非 root + 共享卷：容器里建不了 `data/`、多副本看不到同一份上传都会 500（M6 P11）。
13. nginx 只在启动解析 upstream → 变量 + `resolver 127.0.0.11` 才能 `--scale` 生效（M6 P12）。
14. **本地验收清单必须逐条镜像 CI**：漏了 `pnpm gen:api` → 本地"全绿"、CI 直接红（M6 P16）。
15. 测试必须自带环境（P15）：依赖 shell 里的代理变量/PATH/DB 地址的断言，在别人机器上会静默失效；
    干净 shell 才是真验收环境。
16. 端到端探针本身也会骗人：5s 超时把"接管耗时"量成了探针上界（V6/P21 周边）；数字要写清口径。

**流程**
17. 提案先行、验收包交付、由人拍板——本项目已经因此两次避免了"假绿"（M6 收尾、V 阶段）。

**验证与演练（P1 阶段补充）**
18. **连接参数不能信库默认值**：`websockets` 的 `close_timeout` 默认 10s，供应商不回关闭帧 → 松手后干等 10 秒（P24）。
19. **证据工具本身要先被校准**：探针"发完才收"会把增量时序塌缩（P25）；漏 cookie 会把 503 读成 401（P27）；
    演练的恢复动作必须放 `finally`，否则一次崩溃就把栈留在故障态。
20. **兜底 try 要罩住循环里的每一次依赖调用**：心跳写漏在 try 外，Redis 抖动就让 worker 退出（P26，M6 P9 的补完）。
21. **单身份压测测的是"我们的桶"**：进程内限流 × N 副本 = 配额 ×N；要压供应商必须多身份并行（P1-B §2.7）。

**验收轮补充（P28–P30）**
22. **一个语义可能活在多层**：转写合并 = store→页面→**组件内部 prop-effect**；P28 改了两层仍复发，P30 才补上
    chat Composer 这层。改任何合并语义，先 grep 调用点清零。
23. **测试缝贴着用户路径不够时，贴着组件也来一份**：store 级页面测试全绿，浏览器照样复现——因为组件内部
    合并由 prop 逐事件驱动，store 灌事件测不到（P30 的缝缺口）。
24. **部署不发 Cache-Control = 修了个寂寞**：index.html 无头 → 启发式缓存 → 用户跑上一版 bundle，症状与代码
    bug 肉眼难分（P29）。判定链：nginx access log 拉的是哪个 hash → 容器产物 md5 vs 本地 build。

**PR 首跑补充（P31–P33）**
25. **收口脚本的"标签"与"展开"会各自漂移**：`--list` 写着 `all = unit + contract + scripts`，`all)` 实际只跑
    unit+scripts（P31）——于是"本地全绿、CI 红"（M6 P16）原地复活。写"本地收口"之前先 `--dry-run` 看它**到底要跑什么**；
    回归测试钉展开，不钉标签。
26. **测试断言不许引用"本机恰好存在的文件"**：`data/` 是 gitignored，fixture 断言在干净 checkout 必红（P32）。
    需要本地产物的校验，放进那一层自己的预检（real 层：**花钱之前** exit 2），单测只测 hermetic 的"缺失即拒绝"。

## 交接动作流水（原 9）

## 9. 交接动作清单

0. ~~**本轮动作**：等 PR #18 合入 → 审计线开 PR~~ ✅ **已完成（2026-10-07）**：#18（`15f073e`）与 #19（`f915f20`）均已合入 `main`；收尾只改文档（本节 + §1 + §4 加一行坑）。
1. ~~**用户**：正式验收 **P1 + P2**~~ ✅ **已完成（2026-09-17）**：用户验收通过，结论回填
   `docs/tickets/p1-post-v/ACCEPTANCE.md` §7（浏览器手测第 3 轮 ✅，见 `docs/MANUAL-TESTING.md` §5）。
2. **用户**（小事仍挂着）：轮换三个 key（对话里出现过）；端到端验证"星云等价物"时给百炼应用 **app_id**。
3. ~~**我**（PR 流程）~~ ✅ **已完成**：**PR #8 已合并**（`p1/realtime-asr` → `main`，正文 = ACCEPTANCE.md）。
   首跑 backend 红（P31–P33，本地看不见的三层）→ 已红-绿修完并复跑 `--layer all` 12 条命令全绿 → 复跑 CI → 用户点头 → 合并：
   ```bash
   cd '/root/better resume'
   # 本机 gh 的 TLS：7897 代理没起时，直连被 Watt Toolkit 中间人拦截，需信任其证书链
   #   openssl s_client -connect api.github.com:443 -servername api.github.com -showcerts </dev/null | \
   #     awk '/BEGIN CERT/,/END CERT/' > /tmp/chain.pem
   export SSL_CERT_FILE=/tmp/chain.pem; unset HTTPS_PROXY HTTP_PROXY
   gh pr checks 8 --watch                 # backend/frontend 双 job（含 coverage 底线步）
   gh pr merge 8 --merge                  # 用户点头后
   # 22 端口被拒时：git push ssh://git@ssh.github.com:443/eicon-xyz/better-resume.git <branch>
   cd apps/api && uv run pytest -q --junitxml=/tmp/main.xml   # main 复跑（例数看 xml 读数，别抄进文档）
   # 合并当晚 02:30 UTC：nightly 首跑（schedule 只认默认分支）；次日 gh run list + artifacts
   ```
   **注意**：历史清理时删光了 29 条 run → GitHub 上 workflow 曾"注销"（`gh workflow list` 为空）；PR 事件会重新注册，
   nightly/weekly 要等合并后由 schedule 注册。
4. 后续候选（都要**先提案**）：自动 Redis failover（哨兵/多端点）、>24 并发与供应商 429 行为、讯飞真机、浏览器矩阵。
