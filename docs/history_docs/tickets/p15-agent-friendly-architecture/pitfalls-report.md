# pitfalls-report：智能体重复犯的错误类

## 方法与覆盖

- 扫描范围：`git rev-list --count HEAD` = **254** 个提交，首个提交 `88287ee`（2026-09-13）→ HEAD `b09bbd2`（2026-10-13）；remote `eicon-xyz/better-resume`。工作区未提交改动（p14 在飞）不看。
- 方法：correct 的两步——先按证据把错误分组（同类出现 ≥2 次才成类），再给每类取「能消灭它的最高层」（代码架构 > 类型 > lint·CI > 测试 > 文档）；分组筛查用 architect 的设计红旗：two ways to do one task、hand-synced list、split ownership、information leakage、shallow module。
- 判定参照：`CODING_STANDARDS.md` §1/§2/§4/§6、`AGENTS.md` §开发规范、`docs/DECISIONS.md`（D17 契约生成物 / D22 验证脚本必须真判定 / D23 降级语义）。决策本身（D 号所指的选择）与用户拍板接受的偏差不算坑。
- 证据源与口径：`docs/**/PROBLEMS.md` 是各阶段的问题台账，每条对应一次真实提交；`出处` 的 `文件:行号` 一律按 HEAD `b09bbd2` 的文件版本；引用台账行时 `sha` 取 `git blame` 认定的该行引入提交，引用提交时 `sha` 就是该提交本身。
- 复跑约定：下面的 `频次` 命令原样可跑；命令里的 `$L`（有小节标题的台账）与 `$R`（只有表行的台账）先导出：

```bash
L='docs/history_docs/tickets/m3/PROBLEMS.md docs/history_docs/tickets/m4/PROBLEMS.md docs/history_docs/tickets/m5/PROBLEMS.md docs/history_docs/tickets/m6/PROBLEMS.md docs/history_docs/tickets/p5-auto-failover/PROBLEMS.md docs/history_docs/tickets/p7-shared-rate-limit/PROBLEMS.md docs/history_docs/tickets/v1-verification/PROBLEMS.md docs/tickets/p11-resume-driven-questions/PROBLEMS.md docs/tickets/p12-intent-alignment/PROBLEMS.md docs/tickets/p13-golden-path-e2e/PROBLEMS.md'
R='docs/history_docs/tickets/p1-post-v/PROBLEMS.md docs/history_docs/tickets/p4-nightly-green/PROBLEMS.md'
```

- 排序：按 `频次`（= 证据条数 = 计数命令输出行数）降序。

## 坑频次榜

### P01 失败被静默吞掉：协程没 await、返回值被 void 丢弃、异常留在 task 里
出处：bbe6523 Explain overload failures in the web app and stop losing typed answers；docs/history_docs/tickets/m3/PROBLEMS.md:129 ｜ 883831c Add xunfei AST adapter, WS tickets and the transcription WebSocket；docs/history_docs/tickets/m4/PROBLEMS.md:67 ｜ 2c44464 Add browser audio capture, transcription client, TTS player and page wiring；docs/history_docs/tickets/m4/PROBLEMS.md:138 ｜ fb8d7ed Add the Redis distributed single flight and record the M6 progress；docs/history_docs/tickets/m6/PROBLEMS.md:56 ｜ c2c0c7c Write the M6 acceptance evidence, the problems ledger and the resume draft (M6-T9)；docs/history_docs/tickets/m6/PROBLEMS.md:98 ｜ 3fa7832 feat(v4): second real LLM platform on Aliyun DashScope；docs/history_docs/tickets/v1-verification/PROBLEMS.md:41
原文摘录：「## P10 — 提交失败会清空候选人输入（M2 遗留 UX bug）+ 两次“返回值被吞”」；`onSubmit={(text) => void controller.submitAnswer(text)}` —— `void` 把返回值吞了 ｜ 「## P4 — 接收循环异常被 task 吞掉：调用方永远等不到失败」「异常只留在 task 对象上」 ｜ 「## P11 — jsdom 没有 URL.createObjectURL / 媒体播放：播放器静默不合成」「speak() 的 promise 变成未处理拒绝（void 调用），于是后面的合成根本没发生」 ｜ 「## P4 — 结果回放的模块白名单：测试模型被静默拒绝」 ｜ 「## P8 — 场景配置校验从来没被执行过」「`if not factory.is_configured(binding)` —— 协程对象恒为真值，于是守卫被静默跳过」 ｜ 「## P19 — 流式 usage 没有主动请求：换一家平台就静默丢 token 统计」
频次：6（计数命令：`git grep -n -o -E '^## P?[0-9]+[. ].*(静默|被吞|吞掉|未 await|从来没被执行过)' b09bbd2 -- $L | wc -l`）
哪一层能消灭它：**类型**——让“可能失败/异步的调用”在类型与语法层无法被忽略（必须消费的返回值、禁止 `void <promise>`、禁止未 await 的协程），兜底 `except` 不得把类型错误降级成语义错误；现有只有测试断言与文档规则。

### P02 部署面与浏览器边界的隐式默认值：只有真跑该形态才暴露
出处：2c44464 Add browser audio capture, transcription client, TTS player and page wiring；docs/history_docs/tickets/m4/PROBLEMS.md:119 ｜ c2c0c7c Write the M6 acceptance evidence, the problems ledger and the resume draft (M6-T9)；docs/history_docs/tickets/m6/PROBLEMS.md:124 ｜ c2c0c7c Write the M6 acceptance evidence, the problems ledger and the resume draft (M6-T9)；docs/history_docs/tickets/m6/PROBLEMS.md:135 ｜ c2c0c7c Write the M6 acceptance evidence, the problems ledger and the resume draft (M6-T9)；docs/history_docs/tickets/m6/PROBLEMS.md:146 ｜ 4f57b8b fix(deploy): index.html no-store plus immutable hashed assets; realtime page-regression tests; P29 in ledger；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:13 ｜ 7d4d462 docs(handoff): record the buildx network.host entitlement gate (P45)；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:21
原文摘录：「## P9 — Vite 开发代理没开 WebSocket → 浏览器连不上转写通道」 ｜ 「## P10 — compose 没有迁移步骤：新卷直接 500」「没人跑 alembic」 ｜ 「## P11 — 非 root 容器写不了 data/：上传简历 500」 ｜ 「## P12 — nginx 只在启动时解析一次 upstream：扩容后仍打一个副本」 ｜ P29：「nginx 对 index.html 不发任何 Cache-Control → 浏览器启发式缓存 HTML」 ｜ P45：「nightly 连续两晚全红：buildx 0.37.2 的 bake 同意闸门 + 我们的 `network.host`」
频次：6（计数命令：`{ git grep -n -o -E '^## P?[0-9]+[. ].*(Vite 开发代理|迁移步骤|非 root|nginx)' b09bbd2 -- $L ; git grep -n -o -E '^[|] P[0-9]+ [|].*(index.html|buildx)' b09bbd2 -- $R ; } | wc -l`）
哪一层能消灭它：**代码架构**——部署形态只能有一个受检查的入口、构建/运行参数显式声明，每条隐式默认值都配一条在真跑该形态时变红的断言（现有只有 `compose_smoke.sh` 的几条响应头/非 root 断言，其余靠真机踩）。

### P03 证据工具自身说谎或崩溃，结论被算到被测对象头上
出处：8431916 docs(p1): P1-A acceptance package — realtime ASR evidence, problems P24/P25, stage ticket；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:6 ｜ 2f394be fix(worker): keep beating through a Redis failover; add partition/failover drills and the P1-C pool probe (P1-C/P1-D, P26/P27)；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:9 ｜ 63ec2f8 fix(drills): cold-volume migrate, and probes that survive the faults they inject (P35-P38)；docs/history_docs/tickets/p4-nightly-green/PROBLEMS.md:7 ｜ 720f93b docs(p7): acceptance package, problem ledger and the SKILL/capacity updates；docs/history_docs/tickets/p7-shared-rate-limit/PROBLEMS.md:3 ｜ 43e63db feat(e2e): assert the interview golden path against the fake vendor；docs/tickets/p13-golden-path-e2e/PROBLEMS.md:117
原文摘录：P25「`v3_ws_probe.py` 原来**发完才收**：websockets 客户端会缓冲服务器帧，9 个增量的时间戳全部塌缩到收帧时刻（5.55s），差点把正确实现误判为“不增量”」 ｜ P27「演练探针自身的两个缺陷：① 分区前没登录 → 采到 401 并一度误判 P17 契约被破坏」 ｜ P36「一个正常的限流被报成服务端 bug（`KeyError: 'next_action'`）……不再用 KeyError 冒充结论」 ｜ P42「探针与演练共用同一个限流桶：钉小 rate 把演练自己打成 429」 ｜ 「## 19. DB 落库探针从未工作过：psql 的 `-c` 不做变量插值」
频次：5（计数命令：`{ git grep -n -o -E '^## P?[0-9]+[. ].*(探针|发完才收)' b09bbd2 -- $L ; git grep -n -o -E '^[|] P[0-9]+ [|].*(探针|发完才收)' b09bbd2 -- $R ; } | wc -l`）
哪一层能消灭它：**测试**——探针/演练自己必须有一对会红的对照（已知坏输入必红、探针失败与被测失败可区分），且探针的读写时序先于结论被校准；现有是事后写进台账的教训。

### P04 假时钟与真实时序假设：测试挂死或把正确实现误判成坏
出处：d49e08b Add bulkhead slots and clock-driven deadlines；docs/history_docs/tickets/m3/PROBLEMS.md:72 ｜ 95c908e Fix resilience keys for all four AI links and prove single-flight end to end；docs/history_docs/tickets/m3/PROBLEMS.md:117 ｜ fb8d7ed Add the Redis distributed single flight and record the M6 progress；docs/history_docs/tickets/m6/PROBLEMS.md:47 ｜ 43e63db feat(e2e): assert the interview golden path against the fake vendor；docs/tickets/p13-golden-path-e2e/PROBLEMS.md:111
原文摘录：「## P5 — ManualClock.advance() 只唤醒“已注册”的 sleeper → 测试在任务启动前推时间会永久等待」 ｜ 「## P9 — 并发测试的时序假设：follower 在到达接缝前还有 DB I/O」「用固定次数 `await asyncio.sleep(0)` 等 follower 到接缝……第一次修法（用指标轮询）只在 `sleep(0)` 上循环，同样的问题再犯一次」 ｜ 「## P3 — ManualClock + 轮询循环 = 死循环（M4 的老坑换了个马甲）」 ｜ 「## 18. 存量时序 flake：`test_bounded_wait_raises_a_clear_error`」「测试本身依赖真实 Redis 与真实时间——违反本仓库「时间用注入时钟测」的做法」
频次：4（计数命令：`git grep -n -o -E '^## P?[0-9]+[. ].*(ManualClock|时序)' b09bbd2 -- $L | wc -l`）
哪一层能消灭它：**代码架构**——时钟是一个注入的缝，且“有界等待/重试”这类语义必须能用注入时钟完整表达（消除只能靠真实时间测的路径）；现在是测试层的手写约定「假时钟只用在能显式推进的地方」。

### P05 转义与源码语法卫生：非 raw docstring 的反引号、补丁脚本的二次转义
出处：0e0b24a Add in-process single flight with replay TTL and problem log entries；docs/history_docs/tickets/m3/PROBLEMS.md:57 ｜ 883831c Add xunfei AST adapter, WS tickets and the transcription WebSocket；docs/history_docs/tickets/m4/PROBLEMS.md:93 ｜ 7f5de64 Keep the scene mapping docstring raw after the hygiene guard caught it；docs/history_docs/tickets/m5/PROBLEMS.md:35
原文摘录：「## P3 — M2 遗留：`interview_engine/storage.py` 文档字符串里的 `\`` 触发 SyntaxWarning」「干净环境（CI/新克隆）会重新出现」 ｜ 「## P7 — 转义反复踩坑 → 加源码 hygiene 守卫」「同一类问题出现三次：M2 的 storage.py docstring 反引号（SyntaxWarning）、我自己的 xunfei_ast.py docstring 反引号（又一次 SyntaxWarning）、以及用脚本改代码时 TS 模板串与 shell heredoc 的二次转义」 ｜ 「## P2 — hygiene 守卫第一次抓到我自己（docstring 里的反引号转义）」
频次：3（计数命令：`git grep -n -o -E '^## P?[0-9]+[. ].*(hygiene|反引号|SyntaxWarning)' b09bbd2 -- $L | wc -l`）
哪一层能消灭它：**lint·CI**——`tests/test_source_hygiene.py` 已把 SyntaxWarning 变红（在 lint 层可再上移到 ruff 规则）；补丁脚本的二次转义只能靠“不用脚本改源码”这种架构性消除，目前仍是文档里的约定（`chr(10)`/`chr(36)`）。

### P06 契约生成物漏刷：改了模型只生成一半
出处：1e237c4 Regenerate the OpenAPI document and web types for the media endpoints；apps/web/src/api/schema.d.ts:42 ｜ c3200ee Regenerate web API types for the media endpoints；apps/web/src/api/schema.d.ts:260 ｜ 29ab3ca Regenerate the API types and fix the web fixtures the drift uncovered；apps/web/src/api/schema.d.ts:566
原文摘录：1e237c4 diff `+    "/api/v1/auth/ws-ticket": {`（`schema.d.ts:42`） ｜ c3200ee diff `-        /** Get Speech */` → `+        /** … keep it private. */`（`schema.d.ts:260`） ｜ 29ab3ca 提交信息「M6 added source and summary_pending to the OpenAPI document but only openapi.json was regenerated, so the frontend job failed on check:api: the committed schema.d.ts was stale」＋ diff `+            summary_pending: boolean;`（`schema.d.ts:566`）
频次：3（计数命令：`git log --format='%h %s' --no-merges -E --grep='Regenerate' | wc -l`）
哪一层能消灭它：**lint·CI**——`pnpm -C apps/web check:api` 已在 CI 里（D17 的两处生成物）；缺的是“本地收口与 CI 同一条命令”这一层，M6 P16 与 P31 两次失败模式都出自此处。

### P07 共享状态没有唯一所有者：两个写入方、跑完不留证、跑完不还原
出处：a2a0ff1 feat(interview): classify questions by category and score reports per category；docs/tickets/p11-resume-driven-questions/PROBLEMS.md:5 ｜ 43e63db feat(e2e): assert the interview golden path against the fake vendor；docs/tickets/p13-golden-path-e2e/PROBLEMS.md:35 ｜ 43e63db feat(e2e): assert the interview golden path against the fake vendor；docs/tickets/p13-golden-path-e2e/PROBLEMS.md:71
原文摘录：「## 1. 语料文件被两个 worker 同时写」「同一路径被两个写入方拥有——「先建任务、再派活」只保证任务唯一，没有保证**在途期间的排他**」 ｜ 「## 6. 执行方自证的端到端读数没有留存产物，事后查库无痕」「自证读数要么落盘、要么明说没落盘」 ｜ 「## 12. e2e 每跑一次留一套业务行，不清理」
频次：3（计数命令：`git grep -n -o -E '^## P?[0-9]+[. ].*(两个 worker|两个写入方|留存产物|不清理|共享状态)' b09bbd2 -- $L | wc -l`）
哪一层能消灭它：**代码架构**——每份状态一个所有者（产物路径唯一、在途写入排他），测试与演练动过的跨进程状态由构造还原；现有是 `635ff6e` 的还原用例与 `AGENTS.md` 规则，“两个写入方”仍靠约定。

### P08 一份逻辑被复制成多份手写副本，两份各自演化
出处：0ced2a9 refactor(media): one update-to-event mapping shared by both channels (P8 / media-01)；apps/api/src/better_resume/media/event_map.py:1 ｜ e1ff440 fix(scripts): render the --list layer map from the layer plan (P44)；scripts/verify.sh:12 ｜ c1fcc11 refactor(scripts): drop the forwarding builders, dispatch by name, pin the map verbatim (P9 review)；scripts/verify.sh:61
原文摘录：`event_map.py:1` 「Two adapters carried this block line for line — `xunfei_ast` … and `scripted` … and nothing required them to stay equal: editing one was enough to make the two disagree about what a committed sentence is.」 ｜ `verify.sh:12` 「--list renders the layer plan declared below instead of keeping a second, hand-written copy of it: that copy had drifted in 5 of 21 lines (P44), and a substring test cannot see a wrong command.」 ｜ `verify.sh:61` 「Expanded once, here, so every command string is final text by the time it is printed: the map and the dry-run then show the same characters」
频次：3（计数命令：`git log --format='%h %s' --no-merges -E --grep='shared by both|from the layer plan|by name, pin the map' | wc -l`）
哪一层能消灭它：**代码架构**——一份真源、其余派生；派生不了就让构建在两者不一致时失败（hand-synced list 在架构层被消掉）；两次修法都印证了这一点。

### P09 证据、引证与数字凭记忆写：失真或事后不可复跑
出处：a2a0ff1 feat(interview): classify questions by category and score reports per category；docs/tickets/p11-resume-driven-questions/PROBLEMS.md:26 ｜ 43e63db feat(e2e): assert the interview golden path against the fake vendor；docs/tickets/p13-golden-path-e2e/PROBLEMS.md:103 ｜ 7560c36 docs(audit): re-anchor the drifted citations, record the fixes and fill the acceptance numbers (P8)；docs/audit/units/media.json:49
原文摘录：「## 4. 实现移位导致审计引证失效」「`verify_audit_evidence.py --strict` 从 122/0/0 掉到 110/9/3（12 个 issue 部分或完全失证）」 ｜ 「## 17. 修复轮自述的四处轻微失真（异家族复核抓出）」「自述按演示顺序而非章节顺序写、引文凭记忆转写、计数凭印象」 ｜ `media.json:49` diff `+      "fix_record": { "status": "fixed", …` 把引证锚点从单个行号扩到 `xunfei_ast.py:238-239` 这样的范围
频次：3（计数命令：`{ git grep -n -o -E '^## P?[0-9]+[. ].*(引证|失真)' b09bbd2 -- $L ; git log --format='%h %s' -E --grep='re-anchor the drifted' ; } | wc -l`）
哪一层能消灭它：**lint·CI**——引证由 `verify_audit_evidence.py` 复核（D22 已把“只打印结论、不判定的验证脚本”定为缺陷），但“自述里的数字”还没有会红的检查；这一半只能靠把数字从人写的话里搬进产物。

### P10 缓存语义没有被钉住：负缓存启发式、读缓存忘了写路径失效、进程内缓存跨副本漂移
出处：0e0b24a Add in-process single flight with replay TTL and problem log entries；docs/history_docs/tickets/m3/PROBLEMS.md:47 ｜ c2c0c7c Write the M6 acceptance evidence, the problems ledger and the resume draft (M6-T9)；docs/history_docs/tickets/m6/PROBLEMS.md:75 ｜ 35bbfc0 docs(v1): evidence for V1, V2 and V6 and the capacity report sections；docs/history_docs/tickets/v1-verification/PROBLEMS.md:19
原文摘录：「## P2 — 负缓存只对“有 follower 的失败”生效（与提案语义不符）；future 异常无人取会告警」「我加了个自以为聪明的启发式“没有等待者就不缓存”，与提案……不一致」 ｜ 「## P6 — 热层加了读缓存却忘了失效（T3）」「写路径（出题 / 答题 / finish）没有失效热键；热层 TTL 600s……**过期视图比慢一点的视图更糟**」 ｜ 「## P18 — 场景绑定缓存是“每进程”的：另一个副本继续用旧绑定」「M5 的 `SceneResolver._bindings` **没有 TTL**……多实例下“进程内缓存 + 只在本地失效”= 配置漂移」
频次：3（计数命令：`git grep -n -o -E '^## P?[0-9]+[. ].*(负缓存|忘了失效|每进程)' b09bbd2 -- $L | wc -l`）
哪一层能消灭它：**代码架构**——写路径与失效是同一个所有者的责任（缓存对象自己保证“写后读一致”），TTL 只是兜底；`CODING_STANDARDS.md` §6 的必答问题在文档层已有，仍复发。

### P11 库与协议的默认值、语义假设没有显式化
出处：8431916 docs(p1): P1-A acceptance package — realtime ASR evidence, problems P24/P25, stage ticket；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:5 ｜ 87a7381 docs(v3): evidence for the batch ASR path and the two bugs it exposed；docs/history_docs/tickets/v1-verification/PROBLEMS.md:56 ｜ 87a7381 docs(v3): evidence for the batch ASR path and the two bugs it exposed；docs/history_docs/tickets/v1-verification/PROBLEMS.md:72
原文摘录：P24「`websockets` 库 `close_timeout` 默认 **10s**……`close()` 挂满 10s——松手→final 10.1s」 ｜ 「## P20 — 批量 ASR adapter 的 \`wait()\` 违反协议：socket 在第一帧就断」「`TranscriptionChannel.wait()` 的契约是“阻塞到通道结束”。我的批量 adapter 写成 `if self.failure: raise` → 立即返回……**实现 Protocol 不等于满足契约**」 ｜ 「## P21 — 成功路径不关 WS 握手，客户端报 1006」
频次：3（计数命令：`{ git grep -n -o -E '^## P?[0-9]+[. ].*(违反协议|不关 WS)' b09bbd2 -- $L ; git grep -n -o -E '^[|] P[0-9]+ [|].*(close_timeout)' b09bbd2 -- $R ; } | wc -l`）
哪一层能消灭它：**类型**——把协议语义做成会红的契约测试（`wait()` 在 `stop()` 前必须不返回；成功路径必须显式关闭），并让连接参数没有可依赖的库默认值；现在是“新 adapter 先跑一次真实链路”的人肉纪律。

### P12 测试依赖运行环境：代理变量、DB 地址、本机恰好存在的文件
出处：e0260fd Fix environment-dependent tests and harden the acceptance scripts (M6 acceptance feedback)；docs/history_docs/tickets/m6/PROBLEMS.md:179 ｜ 30d4d12 docs(p1): record P31-P33 and the post-acceptance CI fixes；docs/history_docs/tickets/p1-post-v/PROBLEMS.md:19
原文摘录：「## P15 — 测试依赖了运行环境（M6 验收时被用户的干净 shell 抓出来）」「测试必须自带环境（代理变量、PATH、DB 地址都算环境）。凡是“我这台机器上过、别人那里静默失效”的断言，都是在给未来的验收埋雷」 ｜ P32「fixture 断言不 hermetic……但 `data/` 是 gitignored → 干净 checkout 必红，本机因文件在才绿」「测试里不许出现“我这台机器上恰好有的文件”」
频次：2（计数命令：`{ git grep -n -o -E '^## P?[0-9]+[. ].*(干净 shell|干净 checkout|hermetic)' b09bbd2 -- $L ; git grep -n -o -E '^[|] P[0-9]+ [|].*(hermetic|干净 checkout)' b09bbd2 -- $R ; } | wc -l`）
哪一层能消灭它：**lint·CI**——测试自带环境（代理变量清空、DB 地址显式、文件用 tmp），需要本机资源的断言挪到 preflight；现有做法已把“存在 + pin 一致”挪到真实层预检，规则仍写在 `AGENTS.md`。

## 单次个案

以下条目在自己的阶段台账里各只出现一次，不构成类（按台账编号列出；个别是环境事实而非错误）：

- M3：P1（单飞失败分支漏 settle，follower 永久挂死）、P4（背压断言差一帧）、P7（`TokenBucket.idle` 没按时间投影）、P8（韧性错误 kind 不在 `ChatErrorEvent.kind` Literal 里，被 SSE 兜底降级成 unknown）；P6（pytest 输出重定向丢尾部）是工具事实。
- M4：P2（尾缀合并把单字重叠当重复）、P3（重连预算在连上时归零）、P6（sender 先被 cancel，final 发不出去）、P10（页面级语音测试用全局桩）、P13（脚本说更新了但 git 里没有）。
- M5：P3（按“第 N 次出现”打补丁把文件改坏）、P4（一次答题请求里的两个场景边界）；P0/P1 是预防项与“本机无凭据”的环境事实。
- M6：P2（分布式单飞“空档重跑”）、P5（回放失败结果漏 stage）、P7（Redis 6.0 的 XPENDING/XCLAIM 形状）、P9（worker 把取消当异常）、P13（Docker Desktop 代理）、P14（httpx client 不能进两次上下文）；P0/P1 是环境事实与文档读法。
- V1：P17（会话存储故障应是 503 不是 500）、P22（采集节点没接 destination）、P23（合并规则丢掉批量转写）、P19 之外的平台差异项各只一次。
- P4/P5/P7：P35（三个演练脚本先 seed 后 migrate——同一遗漏在三个脚本各写一遍，接近类但记为一次）、P37/P38（故障演练的前置就绪窗口）、P41（哨兵 TILT）、P43（分区期间认证路径先死）；P42 已并入 P03。
- P11/P12/P13：P11 的 §2/§3/§5/§6，P12 的 §1–§11（除已入类者），P13 的 §1/§2/§3/§4/§5/§7/§8/§10/§11/§13/§14/§15/§16——都是单次发现或流程口径之争。

## 对 agent-friendly 重架构的含义

- 一份逻辑只允许存在一处。凡是“两份必须相等”的关系（真源与副本、标签与展开、两个适配器之间的逐行复制），结构上要么由一份派生，要么在不一致时让构建失败——写成人读的规则不改变任何行为。（P06/P08/P09）
- 让“被忽略的失败”不可表达。可能失败的调用必须在类型或语法层被消费；兜底 `except` 不得把类型错误降级成语义错误；未 await 的协程、被丢弃的返回值、未处理的拒绝都应有会红的检查。（P01/P11）
- 环境必须成为显式入参。时钟、代理、DB 地址、证据目录、连接参数、限流桶——运行环境提供的默认值都要在代码里有一个显式位置，测试不读运行环境的隐式状态。（P04/P11/P12）
- 共享状态一个所有者。产物路径唯一、在途写入排他；测试与演练动过的跨进程状态由构造还原，动过的业务行要么隔离在唯一身份下、要么跑完即清。（P07）
- 部署与浏览器边界只能有一个受检查的入口，每条隐式默认值（缓存头、代理、迁移、属主、upstream 解析）都配一条在真跑该形态时变红的断言。（P02）
- 验证工具本身是被测对象。探针、层地图、计数、引证都要先对已知坏输入红一次，并且真的判定（不是只打印结论）——否则工具会替错误背书。（P03/P08/P09）
- 规则写在文档里却仍复发，说明它落在了错误的层。这三类（转义、缓存、环境）都在 `AGENTS.md`/`CODING_STANDARDS.md` 有原文之后继续发生——同一条规则应当上移到会红的检查。（P05/P10/P12）

## 未覆盖

- 工作区未提交改动（p14 在飞）未看；只扫已提交历史，HEAD 取票面点名的 `b09bbd2`。
- M0–M2 没有问题台账（首个台账是 M3），那段历史的重复只能从提交信息推断，未纳入证据；因此本报告的频次对早期阶段是系统性低估。
- 频次口径是“仓库内被记录到的次数”；改对了但没记录的重复、合并提交正文与 PR/CI 日志里的教训都不在计数内——真实频次只会更高。
- 台账是各阶段自述，其中 P13 §17、P12 §3 已复核出“自述轻微失真”；本报告只采用能对上提交的条目，未逐条复核台账措辞。
- 只跑 git 只读命令与 grep，没有重跑任何测试或脚本，因此不验证每条坑在 HEAD 是否仍可复现。
- 单次个案按台账摘列，未穷举；M3 之前与 p15 之后不在范围内。
- 决策（`docs/DECISIONS.md` 的 D 号）与用户拍板接受的偏差不算坑，一律不计入。
