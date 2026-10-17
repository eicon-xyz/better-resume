# T16 注入时钟的有界等待原语（建议 11 的时间半边）

Type: task
Status: resolved
Blocked by: T13（interview_engine/缓存语义先收口，避免再撞 apps/api 写面）
唯一写入路径: `apps/api/`（红线内：ai_resilience 的等待原语与其测试、tests 里真实 sleep 轮询的调用点清零）

## 五栏

- 范围：读 `apps/api/src/better_resume/ai_resilience/`（假时钟/超时/舱壁）、`apps/api/tests/` 里 `sleep`/轮询形态、`pitfalls-report.md` P04（ManualClock.advance 只唤醒已注册 sleeper、sleep(0) 轮询死循环、老坑换马甲复发 4 次）。
- 唯一写入路径：`apps/api/` 内——等待原语、被点名的测试调用点。
- 验收口径（原始输出贴进 T16-EVIDENCE.md）：
  1. 红演示：复刻历史形态（假时钟 + 轮询循环 = 死锁/死循环）的用例在旧实现上红；
  2. 有界等待原语一个实现（注入时钟可完整表达超时），`grep -rn "asyncio.sleep" apps/api/tests | grep -v "# 允许"` 形态清零或逐条注明豁免；
  3. 全量 pytest 权威读数由出票方串行复跑；你跑定向集全绿并如实记录全量尝试；
  4. `bash scripts/verify.sh --layer scripts` 仍退出 0。
- 红线：不改产品行为（只收窄测试时序表达）；不引依赖；不写真实 sleep 断言；不动 p14/docs；不 commit/push/开 PR。
- 不接受的自由度：不许为过测试放宽等待语义（有界必须真有界）；不许每处调用点各写一份等待逻辑（一个原语多处用）；豁免必须逐条注明理由。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`ai_resilience/wait.py` 的 `wait_until` 成为唯一有界等待原语（注入时钟结算、零间隔拒绝、sleeper 可观测）；tests 里 30 处 `sleep(0)` 归一为 `settle()`、轮询全走原语、17 处真实 sleep 逐条豁免；隔离库全量 1016/0/0/0，覆盖率 wait.py 100%。

### 追记（出票方验收）

- 清扫复核：`asyncio.sleep` 无豁免命中 0；test_wait 五用例绿（junitxml 0 fail）。
- 变异演示：删 `interval <= 0` 守卫 → `test_a_non_positive_interval_is_refused` 判红，恢复逐字节一致（超时结算类变异会让假时钟挂死，刻意不砍）。
- 写入面越界检查：apps/api 之外仅会话前已存在的 p14/用户改动（mtime 已核）。
- 未验证项采纳：RedisFlight.execute 产品循环未走原语、distributed_flight 真实时钟用例——记入验收包未验证清单。
