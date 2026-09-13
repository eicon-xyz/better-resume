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
