# M3 实现问题记录（PROBLEMS）

> 用途：你点名要求"实现过程中遇到的问题要记录下来"。这里是**只记真事**的台账：
> 每个条目 = 症状 / 根因 / 修法 / 证据；包含"发现了但决定不修"的项（标注为**已知偏差**）。
> 条目在实现过程中即时追加，M3-T10 收口时在此复核。

## 索引

| # | 发现于 | 一句话 | 状态 |
| --- | --- | --- | --- |
| P0 | 提案阶段（读代码） | M2 遗留：四个 resilience key 里有三个不满足去重语义前提（回放一开就串号） | 待修（T8） |
| P1 | T2 实现 | 单飞失败分支漏 settle → follower 永久挂死（测试被 timeout 杀掉） | 已修 |
| P2 | T2 实现 | 负缓存只对"有等待者的失败"生效，与提案语义不符；future 异常无人取会告警 | 已修 |
| P3 | T1 运行 | M2 遗留：storage.py docstring 的 \` 触发 SyntaxWarning（干净环境才复现） | 待修（T8） |
| P4 | T3 实现 | 背压断言差一帧（生成器先 append 后 yield，生产者在途多一帧） | 已修（改断言） |
| P5 | T5 实现 | ManualClock 只唤醒已注册 sleeper → 任务启动前推时间导致测试挂死（exit=124） | 已修（测试先 settle） |
| P6 | T5 调试 | 工具坑：pytest 输出重定向后尾部丢失 → 改用 --junitxml 读结果 | 已绕过（写进纪律） |
| P7 | T6 实现 | TokenBucket.idle 未按时间投影 → 惰性淘汰从未生效（测试抓到） | 已修 |
| P8 | T7 联调 | 韧性 kind 不在 ChatErrorEvent Literal → SSE 兜底把 timeout 降级成 unknown | 已修（契约同步） |
| P9 | T8 实现 | 并发测试用 sleep(0) 等 follower，DB await 无法推进 → 误判单飞失效 | 已修（事件+真实小睡轮询） |
| P10 | T9 实现 | M2 遗留：提交失败清空候选人输入；修的过程中返回值又被 void 吞一次 | 已修（前端 115 例绿） |

---

## P0 — resilience key 不满足去重语义前提（M2 遗留）

- **症状（静态发现）**：question_service.build_generation_key 只含 session + 姓名/邮箱；
  follow_up_service 的 key 只有 followup\|{session}\|{question_no}（不含答案摘要）；
  report_service 只有 report\|{session}；chat/service.build_resilience_key 不含 model_ref。
- **根因**：M1/M2 的 resilience 是直通实现（DirectAiResilience），key 只是"占位传参"，
  没有测试证明 key 能区分输入；而 §4.1.5 的 key 家族要求 stage|sessionId|questionNumber|sha256(payload)。
- **为什么现在必须修**：M3 打开回放后，"不同输入命中同一 key"不再只是浪费，
  而是**返回错误结果**（换简历出题命中旧批次、换答案复用旧追问、换模型串流）。
- **修法**：T8 把四个 key 收敛成显式纯函数并单测（同输入同 key / 换任一维度 key 必变 / key 不含原文）。
- **证据**：待 T8 测试输出。

## P1 — 单飞：非缓存失败分支漏了唤醒等待者 → follower 永久挂死

- **症状**：T2 测试跑到第 6 个用例失败后进程不再结束（`timeout 240` 杀进程，exit=124）。
- **根因**：leader 失败时我按"是否保留条目做负缓存"来决定是否 `future.set_exception(...)`，
  于是**不可缓存**的失败（超时）只移除条目、不 settle future —— 已经 `await shield(future)`
  的 follower 永远等不到结果。
- **修法**：把"通知等待者"和"是否保活条目"解耦——**失败一律 settle**（等待者必须知道结果），
  条目是否保留只由 `negative_ttl` 与 `cacheable` 决定。
- **证据**：`tests/ai_resilience/test_singleflight.py::test_followers_see_the_very_same_failure`。

## P2 — 负缓存只对"有 follower 的失败"生效（与提案语义不符）；future 异常无人取会告警

- **症状**：`test_cacheable_failure_is_replayed_then_retried` 红：同一个 schema 失败第二次仍打上游。
- **根因**：我加了个自以为聪明的启发式"没有等待者就不缓存"，与提案
  "FAILED 且在 negative_ttl 内且 cacheable → 重放"不一致；另外 future 上设置异常而无人 await
  会触发 asyncio 的 "Future exception was never retrieved" 噪音。
- **修法**：去掉启发式，缓存只看 TTL/cacheable；`future.add_done_callback` 里消费一次异常，
  既保留语义又消除告警。
- **证据**：同上测试文件 12 例全绿。

## P3 — M2 遗留：`interview_engine/storage.py` 文档字符串里的 `\`` 触发 SyntaxWarning

- **症状**：首次编译时 `SyntaxWarning: invalid escape sequence '\`'`（pytest 警告摘要里可见），
  之后因 pyc 缓存不再出现——**干净环境（CI/新克隆）会重新出现**。
- **根因**：非 raw 字符串里的 `\`` 不是合法转义。
- **修法**：改 raw docstring（`r"""...`）或去掉反斜杠（T8 顺手修，改动一行）。
- **证据**：`uv run python -W error::SyntaxWarning -c "import better_resume.interview_engine.storage"`（T8 复验）。
## P4 — 背压测试断言差一帧（测试假设 vs 实现语义）

- **症状**：`test_backpressure_stops_the_producer_at_the_buffer_limit` 断言 `len(produced) <= 3` 失败（实为 4）。
- **根因**：异步生成器"先执行循环体（`produced.append`）再在 `yield` 处挂起"，
  所以生产者在缓冲已满时会**手里多拿一帧**才阻塞；缓冲帧数仍然是 3（不变式正确）。
- **修法**：断言拆成两条——`broadcast.frame_count <= limit`（真不变式）与
  `len(produced) <= limit + 1`（在途一帧）；不修改实现。
- **证据**：`tests/ai_resilience/test_stream_fanout.py` 34 例全绿。
## P5 — ManualClock.advance() 只唤醒"已注册"的 sleeper → 测试在任务启动前推时间会永久等待

- **症状**：`test_stream_timeout_before_the_first_frame` 挂死，pytest 被 `timeout 120` 杀掉（exit=124），
  连 junit XML 都来不及写；表现为"输出只有进度点、没有失败详情"。
- **根因**：`asyncio.create_task(anext(stream))` 之后只 `await asyncio.sleep(0)` 一次，
  包装器内部的 `clock.sleep(timeout)` 定时任务**还没开始执行**（未注册 waiter），
  此时 `clock.advance(1.0)` 推进了时间但不唤醒任何人；等定时任务真正注册时，
  它的 deadline 已经从推进后的时间起算 → 永远不触发。
- **修法**：测试里显式让出若干次事件循环（`for _ in range(5): await asyncio.sleep(0)`）
  等任务启动后再推进时间。**没有**把"宽容逻辑"塞进 ManualClock：
  时钟语义保持"时间只前进 + 唤醒已注册者"，这类顺序约束写进测试注释，
  否则真正的时序 bug 会被时钟掩盖。
- **证据**：`tests/ai_resilience/test_timeout.py` 7 例全绿；`tests/ai_resilience` 56 例 **0.081s** 跑完。

## P6 — 工具坑：pytest 输出重定向到文件时尾部（失败详情/汇总）丢失

- **症状**：`uv run pytest ... > /tmp/x.log 2>&1` 后文件里只剩进度点（如 `....F.....`），
  没有 traceback、没有 "N passed"；管道（`| tail`）也时常只剩进度行。
- **根因**：本机沙箱下 pytest 终端写入器的后续输出没有落到重定向文件里（未定位到 pytest 侧原因，
  疑似与 harness 的输出捕获/缓冲有关）；`timeout` 杀进程时也会丢掉尾部。
- **修法（今后照做）**：需要失败详情时用 **`--junitxml=/tmp/junit.xml`** 再解析 XML
  （`testsuite` 的 tests/failures + `failure.text`），或用 `-x` 先停在一个失败上。
  验收命令矩阵里同时保留 exit code 与 junit 计数，避免"看起来绿了"。
- **证据**：`python3 -c "import xml.etree.ElementTree ..." /tmp/junit.xml` → `tests 56 failures 0 time 0.081`。
## P7 — TokenBucket.idle 只在 take() 里补桶 → 惰性淘汰永远无效

- **症状**：`test_full_registry_evicts_idle_buckets` 红：`tracked_identities == 3`（上限 2），
  空闲桶没有被清掉。
- **根因**：`_tokens` 只在 `take()` 时按时间补充，而 `idle` 属性直接比较 `_tokens` 与容量——
  一个"早就该补满"的桶在没被再次访问前看起来仍然是空的，于是永远不满足淘汰条件。
  （先写测试的价值就在这：单看实现很难发现"惰性淘汰其实一次都没生效"。）
- **修法**：`idle` 按当前时钟**投影**补充后的令牌数再比较容量。
- **证据**：`tests/ai_resilience/test_ratelimit.py` 6 例全绿；HTTP 侧 8 例全绿（合计 14 例）。
## P8 — 韧性错误 kind 不在 M1 的 `ChatErrorEvent.kind` Literal 里 → SSE 生产任务崩成 "unknown"

- **症状**：`test_stream_error_frame_is_persisted` 红：客户端收到 `{"kind":"unknown","message":"internal error while streaming"}`，
  真实的 `timeout` 分类丢失；日志里 `chat_stream_crashed` 带一条 pydantic ValidationError。
- **根因**：`ChatErrorEvent.kind` 是 `Literal["retryable","non_retryable","vendor","duplicate_request","unknown"]`，
  而 M3 的分类是 `timeout/overloaded/unavailable/invalid`；构造错误帧时 pydantic 直接抛错，
  被 `http/chat.py` 的兜底 `except` 吞成 "unknown"——**分类信息在最外层被静默降级**。
- **修法**：把韧性四态并入该 Literal，并在注释里写明两套分类并存的原因；
  同时更新三条 M2 契约测试（502 → 504/timeout，503/unavailable 用于熔断与舱壁）。
- **为什么值得记**：这是"跨里程碑契约漂移"的典型——单测全绿、端到端一跑就露；
  也说明兜底 `except` 会把"类型错误"伪装成"上游抖动"。
- **证据**：`tests/test_chat_api.py::test_stream_error_frame_is_persisted` 绿；后端 407 例全绿。
## P9 — 并发测试的时序假设：follower 在到达接缝前还有 DB I/O

- **症状**：`test_concurrent_identical_chat_streams_share_one_vendor_call` 断言 `gateway.calls == 1` 失败（实为 2），
  单飞 follower 计数为 0——第二个请求另起了一次上游调用。
- **根因（两次踩）**：
  1) 用固定次数 `await asyncio.sleep(0)` 等 follower 到接缝，但 `ChatService` 在调用 `run()` 前
     有多次数据库往返；**`sleep(0)` 不让事件循环去 poll socket**，DB await 根本没机会完成，
     于是我在 follower 还没进接缝时就 `release`，leader 的流结束、条目被清理，follower 自然另起炉灶；
  2) 第一次修法（用指标轮询）只在 `sleep(0)` 上循环，同样的问题再犯一次。
- **修法**：用"事件 + 有限真实小睡轮询"同步：先 `await gateway.started.wait()` 确认 leader 已打上游，
  再以 `asyncio.sleep(0.005)` 轮询 `singleflight_follower == 1`（上限 1s）后才放行。
- **证据**：`tests/test_resilience_concurrency.py` 8 例全绿，含"两路并发聊天流 → 上游恰好 1 次"。
## P10 — 提交失败会清空候选人输入（M2 遗留 UX bug）+ 两次"返回值被吞"

- **症状**：T9 新用例 `keeps the typed answer when the backend sheds load` 失败：
  429 之后输入框内容为空——**候选人写了几百字的回答，一次限流就没了**。
- **根因（三层，逐层暴露）**：
  1. `AnswerComposer` 在 `onSubmit(value)` 之后**立刻** `form.reset()`，与提交成败无关；
     M2 时没有"可重试的过载错误"，所以没暴露。
  2. 修法第一步把 `onSubmit` 契约改成 `Promise<boolean>`，但页面仍写成
     `onSubmit={(text) => void controller.submitAnswer(text)}` —— `void` 把返回值吞了，
     组件收到 `undefined`，于是照样清空。测试第二次抓到。
  3. 用脚本打补丁时把 TS 模板字符串二次转义（`\`` 与 `\${copy}`），
     vite/oxc 直接报 "Invalid Unicode escape sequence" 与字面量 `${copy}`；
     改用 `chr(92)/chr(36)` 构造字符串后正常。
- **修法（最终）**：受控 textarea + `onSubmit: (text) => Promise<boolean> | boolean | void`，
  仅当返回 `false` 之外才清空；房间控制器在过载失败时回 `false` 并提示
  "本题分数未记录，可直接重试"。
- **证据**：前端 115 例全绿（104 → 115）、eslint 0 warning、`tsc --noEmit` 干净。
