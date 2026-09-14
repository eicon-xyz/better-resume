# M6 实现问题记录（PROBLEMS）

> 沿用 M3–M5 的台账纪律：每条 = 症状 / 根因 / 修法 / 证据；含"发现了但不修"的项（标注**已知限制**）。
> 实现过程中即时追加，M6-T9 收口时复核。

## 索引

| # | 发现于 | 一句话 | 状态 |
| --- | --- | --- | --- |
| P0 | 提案阶段（环境核查） | Docker 又能用了（daemon 可达）→ kill 实例验收可以真跑，但镜像构建耗时需计入 | 已知事实 |
| P1 | 提案阶段（读文档） | D07 写"分布式单飞只留接口不写 Lua"，M6 要把它变成**被验收覆盖**的实现 —— 冲突要在文档里讲清 | 预防中（T8 验收覆盖） |
| P2 | T2 实现 | 单飞 follower 在 owner 完成并释放后"抢占空档"重跑了一遍上游（结果键明明已有） | 已修（先查结果再抢锁） |
| P3 | T2 测试 | ManualClock 碰上轮询循环 → 永不前进的死循环（exit=124） | 已修（有界等待用真实短超时） |
| P4 | T2 实现 | 结果编解码白名单只认 better_resume.* → 测试用本地模型时静默不回放（表现像功能没生效） | 已修（测试改用真实项目模型 + 文档写明约束） |
| P5 | T2 实现 | 回放失败结果时重建异常漏了 stage 参数 → TypeError（缓存命中路径才炸） | 已修（错误负载带 stage） |

---

## P0 — 环境变化：Docker 恢复可用

- **事实**：M2–M5 期间本机 Docker daemon 不可用（改用原生 Postgres 5433 + Redis 6379），
  本次核查发现 daemon 可达（29.6.2 / compose v5.3.1，且已有其他容器在跑）。
- **影响**：M6 的 compose 形态与 kill 实例 drill 可以真跑（不再需要"两个本地 uvicorn"的替代方案）；
  代价是首次镜像构建需要时间，验收文档要记录环境与耗时。
- **证据**：`docker info` 输出 ServerVersion=29.6.2；`docker compose version` = v5.3.1。

## P1 — D07 与 M6 的表面冲突（诚实原则的正确读法）

- **症状（读文档发现）**：D07 写"分布式单飞只留接口不写 Lua 实现（诚实原则，吸取原项目默认关闭的死代码教训）"，
  而 §12.4 的 M6 又要求"分布式模式（Redis 单飞/锁）"。
- **读法**：D07 约束的是 **M0 阶段**：不要在还没有验收需求时先写一套默认关闭的实现。
  M6 的需求来了，实现就必须**被验收覆盖**（T8 在 `distributed=true` 下 kill 实例），
  否则才是死代码。我们也不写旧项目那套 6 段 Lua + fencing 全谱，而是 SET NX + owner token + 结果键的最简等价物。
- **证据**：待 T8 的 drill 输出。


## P2 — 分布式单飞的"空档重跑"竞态（最值得记的一条）

- **症状**：两实例并发同 key，上游仍被调用 2 次；日志出现 `flight_takeover`（第二实例声称接管）。
- **根因**：我的循环是「先抢 owner，抢不到再查结果」。owner 完成时**先写结果、再释放 owner**，
  于是存在一个瞬间：owner 键已消失、结果键已存在——第二个实例在这一刻 `SET NX` 成功，
  于是把已经完成的活又干了一遍（而且它连结果都没查）。
- **修法**：循环改成「**先查结果，再抢 owner**」；只有结果缺席时才抢。语义上更准确：
  owner 消失 + 结果存在 = 已完成；owner 消失 + 无结果 = 真的掉线，可以接管。
- **证据**：tests/test_distributed_flight.py::test_two_instances_call_the_vendor_once（calls == 1）。

## P3 — ManualClock + 轮询循环 = 死循环（M4 的老坑换了个马甲）

- **症状**：`test_waiting_is_bounded_and_reports_overload` 挂死，pytest 被 timeout 杀（exit=124）。
- **根因**：我用 ManualClock 测"等待超时"，但超时判定是 `clock.now() >= deadline`，
  而 ManualClock 只在测试显式 `advance()` 时前进；循环里的 `clock.sleep()` 于是永远等不到唤醒。
- **修法**：**有界等待**这类用真实长跑语义的用例改用真实短超时（wait_seconds=0.1）；
  假时钟只用在"能显式推进"的地方（锁的续租/过期）。写进测试注释与台账。
- **证据**：同用例改为真实 0.1s，断言 AiOverloaded 且总耗时 < 1s。

## P4 — 结果回放的模块白名单：测试模型被静默拒绝

- **症状**：`test_result_is_replayed_across_instances` 断言 calls == 1 失败（实为 2），但没有任何报错。
- **根因**：跨实例回放要把 Pydantic 值序列化并重建类型；我只允许 `better_resume.*` 的模块，
  而测试里定义的模型位于 `tests.*` → `_encode` 返回 None → 静默不回放（安全设计正确，可观测性不足）。
- **修法**：测试改用真实项目模型（`interview_engine.evaluation.ScoreResult`）；
  同时把"不可编码 → 不回放"写进模块 docstring，并在 `_encode` 返回 None 时记 debug 日志。
- **证据**：同用例绿灯；`test_foreign_modules_are_refused` 断言 `os.system` 之类的负载被拒绝。

## P5 — 回放失败结果时重建异常漏参数

- **症状**：`test_cacheable_failure_is_replayed` 抛 TypeError: missing keyword-only argument: stage。
- **根因**：错误负载只存了 kind/message，重建 `AiInvalid(message, stage=...)` 时没有 stage；
  这条路径只在"命中了失败缓存"时才走到，单实例测试根本碰不到。
- **修法**：错误负载带上 `stage`，重建时传回。
- **证据**：同用例绿灯（两实例只调用一次上游，且第二次拿到同类异常）。

---

## P6 — 热层加了读缓存却忘了失效（T3）

- **症状**：T3 让 `restore` 先读热快照，结果 6 个已存在的报告/恢复测试变红：答题/完成之后再看
  restore，拿到的是**旧的**进度（`answered` 少 1、`current_question_no` 停在上一步）。
- **根因**：`RestoreService.derive()` 之后写热键，但写路径（出题 / 答题 / finish）没有失效热键；
  热层 TTL 600s，测试与真实用户都会在这段时间里读到过期视图。
- **修法**：`http/interview.py` 里三个写接口统一调 `_invalidate_hot(...)`。原则写进代码注释：
  **过期视图比慢一点的视图更糟**。热层只是缓存，真值永远在 Postgres。
- **证据**：tests/test_hot_state.py（失效用例）+ 6 个回归用例转绿；drill 里 kill 前后 restore 视图一致。

## P7 — Redis 6.0 的 XPENDING/XCLAIM 形状（T4）

- **症状**：`test_unacked_jobs_are_reclaimed_after_a_crash` 连续三种失败：`ResponseError: syntax error`、
  `TypeError: unhashable type: 'dict'`、`ValueError: not enough values to unpack (expected 3, got 1)`。
- **根因**：三件事叠在一起。① `XPENDING key group IDLE ms -` 这种带 IDLE 过滤的形式是 Redis 6.2+，
  我们的下限是 6.0（本机 6.0.16 + compose 的 redis:7）；② redis-py 的 `xpending_range(min={...})`
  不接受 dict；③ `XAUTOCLAIM` 返回 `(cursor, entries, deleted)`，而 **`XCLAIM` 只返回条目列表**，
  我按 XAUTOCLAIM 的形状解包了。
- **修法**：用最朴素的 `XPENDING key group - + 100`（它本来就带每条的 idle 时间），在 Python 侧按
  `time_since_delivered >= min_idle_ms` 过滤，再让 `XCLAIM` 在服务端二次确认；解包改成
  `for claimed_id, fields in entries`。
- **证据**：tests/test_job_queue.py 7 例全绿；drill 的 redis key sample 里能看到 `br:jobs:dead`（重试耗尽）。

## P8 — 场景配置校验从来没被执行过（M5 遗留，M6 发现）

- **症状**：新增 worker API 测试时出现 `RuntimeWarning: coroutine 'OpenAiCompatFactory.is_configured'
  was never awaited`。也就是说"场景没配好就报错"的守卫**一直没生效**。
- **根因**：`GatewayFactory.is_configured` 在协议里是同步的，`XingyunGatewayFactory` 也是同步实现，
  但 `OpenAiCompatFactory` 因为要查模型注册表写成了 `async def`；`SceneResolver.resolve()` 直接
  `if not factory.is_configured(binding)` —— 协程对象恒为真值，于是守卫被静默跳过，
  真正的报错退化成 `build()` 里的"环境变量 XX 未设置"（信息更少）。
- **修法**：resolver 侧统一成"同步或异步都接受"（`inspect.isawaitable`），并给工厂加可选
  `credential_hint()`，把 503 的文案变成"set BR_DEEPSEEK_API_KEY / XINGCHEN_API_KEY and XINGCHEN_API_SECRET"。
  测试先红后绿（新增 `AsyncFakeFactory` 用例，断言守卫会拦下未配置的场景）。
- **教训**：**没有 await 的协程是最安静的 bug**——它让"检查"变成"永远通过"。测试里加 RuntimeWarning 断言成本极低。

## P9 — worker 被信号打断后把"取消"当异常抛出，任务永远排队（T4/T5）

- **症状**：drill 跑到 finish 后，报告 `summary` 30s 都没出现；`XPENDING` 为 0、状态键停在
  `status=queued`；worker 容器日志最后是一段 `redis.exceptions.TimeoutError: Timeout reading from redis:6379`。
- **根因**：两层。① compose 重建容器时 worker 收到 SIGTERM，而它正阻塞在 `XREADGROUP BLOCK 500`；
  redis-py 把"被取消的读"包装成 `TimeoutError`，这个异常从 `serve()` 逃出去 → 进程非零退出、容器死掉；
  ② redis-py 8 的默认 `socket_timeout` 是 5s，阻塞读没有和 block 窗口对齐。
- **修法**：① `serve()` 的循环体 try/except：Redis 抖动记 warning + 有界退避后继续，只有
  `CancelledError` 才向上抛（worker 不该被一次 Redis 打嗝杀死）；② `JobQueue` 显式设置
  `socket_timeout`（默认 15s）并新增 `blocking_block_ms()` 把 block 窗口压在 socket 超时之下。
- **证据**：tests/test_worker_loop.py（瞬时 Redis 错误后循环继续、干净停止时删心跳）+ 之后的 drill
  里 worker 成功把 summary 写进报告。

## P10 — compose 没有迁移步骤：新卷直接 500（T5）

- **症状**：drill 第一步 `PUT /api/v1/scenes/chat` 返回 500，日志是
  `asyncpg.exceptions.UndefinedTableError: relation "llm_scene_bindings" does not exist`。
- **根因**：M0 的 compose 只有 api/worker/postgres/redis，**没人跑 alembic**：卷是 M1 时代建的，
  缺 M5 的表；镜像里也没 `COPY alembic.ini`/`COPY migrations`。
- **修法**：加一次性 `migrate` 服务（同镜像、命令 `alembic upgrade head`），api/worker 用
  `depends_on: {migrate: {condition: service_completed_successfully}}`；Dockerfile 补 COPY 两个路径；
  清单测试断言这条依赖存在。
- **证据**：`docker compose ps` 里 `migrate-1 Exited(0)`，之后 PUT scenes 200。

## P11 — 非 root 容器写不了 data/：上传简历 500（T5）

- **症状**：`POST /interview/sessions/{id}/questions` 500，
  `PermissionError: [Errno 13] Permission denied: 'data'`。
- **根因**：`WORKDIR /app` 由 root 创建，`COPY --chown=app:app` 只改了拷进去内容的属主，
  目录本身仍是 root:755 → 非 root 进程无法 `mkdir data/resumes`。
- **修法**：镜像里 `RUN mkdir -p /app/data/resumes /app/data/tts && chown -R app:app /app/data`；
  同时给 api 挂共享命名卷 `uploads:/app/data` —— 多实例下简历必须**每个副本都看得见**，
  这也是"状态在 Postgres/Redis，文件在共享卷"这条不变量的落地。
- **证据**：compose smoke 的 non-root 检查 + drill 里上传出题成功。

## P12 — nginx 只在启动时解析一次 upstream：扩容后仍打一个副本（T5）

- **症状**：`--scale api=2` 之后连打 10 次 `/healthz`，`X-Instance-Id` 只有一个值；
  另外 api 容器重建后 nginx 直接 502（upstream IP 已失效）。
- **根因**：`upstream { server api:8000; }` 里 nginx 只在加载配置时解析一次 DNS，
  Docker 的内嵌 DNS 之后返回几个地址它都不看。
- **修法**：`resolver 127.0.0.11 valid=10s` + 把目标写成变量
  `set $api_upstream http://api:8000; proxy_pass $api_upstream$request_uri;`
  （变量形式必须自己拼 URI）。这样扩容/重建都能在 `valid` 窗口内被发现。
- **证据**：round-robin 12 次拿到两个不同实例 id（compose smoke 的 "nginx reached at least two api instances"）。

## P13 — 构建期网络：Docker Desktop 的 VM 到不了 WSL 里的代理（T5/T8）

- **症状**：重新构建镜像时 `uv sync` 报 `Failed to fetch https://pypi.org/simple/hatchling/`；
  换成 npm 构建则是 `ECONNREFUSED 127.0.0.1:7897`。
- **根因**：本机出口代理跑在 WSL 发行版的 127.0.0.1:7897，而构建容器在 Docker Desktop 的 VM 里：
  桥接下 `127.0.0.1` 是容器自己，`--network=host` 又是**VM 的** host 网络，都不是 WSL 的 loopback。
  我还试过把代理写进 `~/.docker/config.json` 的 `proxies`（反而让 daemon 自带的
  `http.docker.internal:3128` 路径失效，已回滚）。
- **修法/结论**：保留 `build.network: host` 并把代理留在**环境变量**里（compose 会把
  HTTP_PROXY/HTTPS_PROXY 自动转成 build args），先 `docker compose build api` 验证再起栈；
  这条写进 PROBLEMS 而不是写进 compose，因为它是**本机环境**的特性，不该污染部署清单。
- **证据**：`docker compose build api` 成功；T5 smoke/T8 drill 的完整链路都在这之后跑通。

## P14 — 两处小坑（测试与脚本）

- **httpx 客户端不能进两次上下文**：drill 的 `_session()` 里先发了一次请求（客户端自动 open），
  调用方再 `with client` 就抛 `RuntimeError: Cannot open a client instance more than once`；
  改成 `@contextlib.contextmanager` + `finally: client.close()`。
- **指纹键前缀别靠猜**：drill 最初用 `br:lock:*`/`br:hot:*`/`br:flight:*` 统计 Redis 键，
  结果全是 0 也解释不出原因。现在 drill 同时打印**它统计用的原始 key 样本**，
  让"0"变成可核对的事实（对照 `locks.py`/`hot_state.py`/`distributed.py` 里的键构造）。

## P15 — 测试依赖了运行环境（M6 验收时被用户的干净 shell 抓出来）

- **症状**：用户在自己的 root shell 里跑 `uv run pytest -q`：5 个失败。4 个是
  `ConnectionRefusedError ('127.0.0.1', 5432)`，1 个是
  `test_client_survives_malformed_no_proxy: assert True is False`（httpx 客户端 `trust_env` 没被兜底）。
- **根因（两条，都是测试自身的问题）**：
  1. **代理用例依赖环境变量集合**：用例 monkeypatch `NO_PROXY=[::1]`，指望 httpx 构造时抛
     `InvalidURL: Invalid port: ':1]'`。但 urllib 扫环境时只取**第一个**后缀为 `_proxy` 的键
     （大小写不敏感），用户 shell 里先有一个无害的小写 `no_proxy`，于是 httpx 没抛、兜底没触发。
     我的机器因为小写 `no_proxy` 里也含 `[::1]` 才一直绿——**测试在别人的环境里静默失效**。
  2. **需要数据库的用例没声明 `migrated_database` fixture**：没导出 `BR_DATABASE_URL` 时它们直接
     连默认 5432 并炸出一屏 asyncpg traceback，而不是像其他用例那样 `skipped: postgres not reachable`。
     审计结果：全量 645 例里恰好这 4 例（`test_ratelimit_http.py` 的 `tight_client` 两个用例、
     `test_resilience_concurrency.py` 里两个自建 client 的用例）。
- **修法**：
  1. 代理用例先把所有 `*_proxy` 环境变量删干净（`monkeypatch.delenv`）再设 `NO_PROXY=[::1]`；
     另加一条**确定性**孪生用例（monkeypatch `httpx.AsyncClient` 抛 `InvalidURL`）覆盖兜底分支，
     从此与 shell 无关。复现命令：`env no_proxy=localhost NO_PROXY=localhost uv run pytest tests/llm_gateway/test_openai_compat.py`
     （修前 1 failed，修后 0 failed）。
  2. 三个 fixture/用例补 `migrated_database`：没库时整组 skip（`124 → 128 skipped`，failures 4 → 0）。
  3. 顺带把"uv 不在 PATH"这类前置摩擦做掉：两个 shell 脚本自己找 `$HOME/.local/bin/uv` 并提示
     `export PATH=...`；README 的本地开发段补上可直接复制的 `BR_DATABASE_URL`(5433)/`BR_REDIS_URL`(6379)。
- **教训**：**测试必须自带环境**（代理变量、PATH、DB 地址都算环境）。凡是"我这台机器上过、别人那里
  静默失效"的断言，都是在给未来的验收埋雷；干净 shell 才是真验收环境。

## P16 — 漏了前端生成物：CI 抓住的契约漂移（M6 PR #6）

- **症状**：PR #6 的 frontend job 失败（50s），backend job 绿；而我在本机跑 lint / typecheck / vitest 全绿。
- **根因**：M6 给 `RestoreResponseView` 加了 `source`、给 `InterviewReportView` 加了 `summary_pending`，
  我只按 D17 重跑了 `export_openapi.py`，**漏了 `pnpm gen:api`**（`src/api/schema.d.ts` 是第二份生成物）。
  CI 的 `pnpm -C apps/web check:api` 一比就露；本地那份"验收清单"（ACCEPTANCE §5）当时也漏了这一步，
  所以本地看起来全绿——**验收矩阵没对齐 CI，就等于没验**。
- **修法**：`pnpm -C apps/web gen:api` 重新生成（+10 行：`source: string`、`summary_pending: boolean`）；
  生成类型把这两个字段标成**必填**（它们有 default），于是两个 web 测试夹具要补字段
  （`radar.test.ts`、`InterviewReportPage.test.tsx`）→ `tsc` 立刻报出来，这正是生成物该起的作用。
  ACCEPTANCE §5 补上 `check:api` 这一行。
- **证据**：本地 `pnpm -C apps/web typecheck` 0 / `lint` 0 / `vitest` 158 passed；提交生成物后
  `pnpm -C apps/web check:api` exit 0；CI frontend job 重跑转绿。
- **教训**：**本地验收清单必须逐条镜像 CI**（D17 的两处生成物 + schema.d.ts），否则"我这儿全绿"只是
  少跑了一步的错觉。
