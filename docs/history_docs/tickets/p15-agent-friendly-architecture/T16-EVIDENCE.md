# T16 证据：注入时钟的有界等待原语

## 意图复述

- 在 ai_resilience 里落一个基于注入时钟的有界等待原语，测试里所有「等条件成立」的轮询都走它，不再各处手写 sleep 轮询。
- 假时钟能完整表达超时：预算按 clock.now() 结算、等待只在时钟上注册 sleeper，既不空转也不依赖真实时间。
- 真实 I/O 的等待用同一原语配 SystemClock；`apps/api/tests` 里的 `asyncio.sleep` 要么清零，要么逐条 `# 允许：<理由>`。

## 红演示（旧实现上红）

先写 `tests/ai_resilience/test_wait.py`（当时 `wait_until` 还不存在），原始输出：

```
ERROR collecting tests/ai_resilience/test_wait.py
ImportError while importing test module '/root/better resume/apps/api/tests/ai_resilience/test_wait.py'.
tests/ai_resilience/test_wait.py:9: in <module>
    from better_resume.ai_resilience import ManualClock, wait_until
E   ImportError: cannot import name 'wait_until' from 'better_resume.ai_resilience'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.16s
```

历史形态对照（一次性脚本 `/tmp/t16_red_shape.py`，不留在仓库）：左半是 P04 的形态——假时钟 + `sleep(0)` 轮询循环；右半是原语。

```
legacy RED: 轮询循环没看见注入时钟，空转 0.50s
primitive: 注册到注入时钟上的 sleeper = 1
primitive GREEN: waited 1s on the injected clock for condition（真实耗时 0.000s）
```

## 验收命令与原始输出

### 1. 形态清零

```
$ grep -rn "asyncio.sleep" apps/api/tests | grep -v "# 允许"
grep exit=1
```

无输出（exit=1）：要么走 `tests/support.py` 的 `settle()`，要么逐条带 `# 允许：<理由>`。

### 2. 定向集（隔离库 br_t16_verify）

```
$ cd apps/api && uv run pytest tests/ai_resilience tests/media/test_adapter_contract.py tests/media/test_xunfei_ast.py tests/media/test_qwen_asr.py tests/media/test_paraformer_rt.py tests/test_worker_health.py tests/test_resilience_concurrency.py tests/test_chat_service.py tests/test_chat_api.py tests/test_media_tts_api.py tests/test_hot_state.py tests/test_distributed_lock.py tests/test_distributed_flight.py tests/llm_gateway/test_scene_binding_store.py tests/interview_engine/test_answer_service.py --junitxml=/tmp/t16_targeted.xml
233 passed, 2 warnings in 27.95s
```

### 3. 全量（隔离库 br_t16_verify，跑完已 drop）

```
$ cd apps/api && uv run pytest --junitxml=/tmp/t16_full2.xml
1016 passed, 3 warnings in 180.67s (0:03:00)
junit: tests=1016 failures=0 errors=0 skipped=0
```

### 4. scripts 层

```
$ bash scripts/verify.sh --layer scripts
structure ok: 10 units / 122 issues / 340 citations
ALL PASS (12 commands) -- evidence: var/evidence/20261017T055318Z-scripts
```

### 5. coverage 层

```
$ bash scripts/verify.sh --layer coverage
src/better_resume/ai_resilience/wait.py                      21      0   100%
  ai_resilience: 96.4% (floor 90.0%)
floors ok
ALL PASS (2 commands) -- evidence: var/evidence/20261017T055404Z-coverage
```

### 6. 格式与引证门禁

```
$ uv run ruff format --check && uv run ruff check
272 files already formatted
All checks passed!

$ uv run --project apps/api python scripts/verify_audit_evidence.py --strict
verifiable: 122  partial: 0  unverifiable: 0
```

## 豁免清单（17 行，逐条理由）

```
interview_engine/test_answer_service.py:62:            await asyncio.sleep(self._delay)  # 允许：fake 供应商延迟，模拟系统边界
llm_gateway/test_scene_binding_store.py:116:        await asyncio.sleep(0.01)  # 允许：等真实 wall clock 跨过 updated_at 的写入分辨率
media/test_paraformer_rt.py:71:            await asyncio.sleep(0.01)  # 允许：fake 供应商分帧节奏
media/test_paraformer_rt.py:113:        await asyncio.sleep(0.05)  # 允许：让真实会话任务把缓冲音频送到 fake 供应商
media/test_xunfei_ast.py:83:            await asyncio.sleep(0.01)  # 允许：fake 供应商分帧节奏
media/test_xunfei_ast.py:175:            await asyncio.sleep(0.02)  # 允许：推进假时钟后仍需真实事件循环收发 WS 帧
support.py:15:        await asyncio.sleep(0)  # 允许：只让出事件循环，不推进时钟、不等待真实时间
test_chat_api.py:42:                await asyncio.sleep(self._delay)  # 允许：fake 供应商延迟，模拟系统边界
test_chat_service.py:61:                await asyncio.sleep(self._delay)  # 允许：fake 供应商延迟，模拟系统边界
test_chat_service.py:220:            await asyncio.sleep(0.01)  # 允许：消费侧模拟慢客户端
test_chat_service.py:225:    await asyncio.sleep(0.05)  # 允许：等 fake 供应商的流式延迟走完，取消点落在流中途
test_distributed_flight.py:67:    await asyncio.sleep(0.05)  # 允许：让第二个实例的真实 Redis 轮询进入等待
test_distributed_lock.py:55:            await asyncio.sleep(0.02)  # 允许：真实 Redis 临界区需要真实重叠窗口
test_distributed_lock.py:158:        await asyncio.sleep(0.15)  # 允许：Redis PX 是真实时间，短 TTL 只能真等
test_distributed_lock.py:175:            await asyncio.sleep(0.45)  # 允许：验证续租要跨过两个真实 TTL
test_media_tts_api.py:30:            await asyncio.sleep(self.delay)  # 允许：fake 供应商延迟，模拟系统边界
test_resilience_concurrency.py:199:            await asyncio.sleep(self._delay)  # 允许：fake 供应商延迟，模拟系统边界
```

被换成原语的轮询点：`test_worker_health.py`（心跳 2 处）、`test_resilience_concurrency.py`（follower 指标）、`media/test_xunfei_ast.py`（原 `wait_for` 辅助函数删除，6 处调用改原语）、`media/test_adapter_contract.py`（`_press`）、`test_chat_service.py`（落库轮询）、`test_hot_state.py`（过期）。30 处 `asyncio.sleep(0)` 收进 `tests/support.py::settle`。

## 实现决定交代

| 决定 | 为什么 | 已知代价 / 升级路径 |
| --- | --- | --- |
| 原语独立成 `ai_resilience/wait.py`，不塞进 `timeout.py` | `timeout.py:56-71` 被审计单元 ai-09 逐字引证，插入代码会让 `verify_audit_evidence.py --strict` 红 | 多一个小文件；若将来 timeout 语义合并，需同时重锚 ai-09 引证 |
| `wait_until(condition, timeout, clock, interval, description)`：一次实现，同步/异步谓词都收 | 一个原语多处用；超时按 `clock.now()` 结算，假时钟能完整表达 | 调用方要显式给 `timeout`；`interval` 是唯一的真实时间成本 |
| `interval <= 0` 直接 `ValueError` | `sleep(0)` 轮询正是 P04 的历史形态：假时钟推进它看不见，还空转 | 无；默认 0.01 覆盖常规调用 |
| `ManualClock.pending_waiters` 只读属性 | 测试能先看到 sleeper 已注册再推进，消灭「advance 早于注册 = 永久等待」的猜测 | 为测试暴露一个只读计数，不改时钟语义 |
| 测试侧唯一让出事件循环入口 `tests/support.py::settle` | 30 处 `asyncio.sleep(0)` 是让出循环而非等待，逐条豁免会把门禁稀释 | 测试多一个导入；`settle` 内部那一行是唯一 `# 允许` 的 sleep(0) |
| 真实 I/O 的等待仍走同一原语 + SystemClock | 外部世界（Redis/DB/fake 供应商 socket）本来就是真实时间，原语只统一「有界」与「一处实现」 | 这些用例的等待仍是真实时间，已在豁免清单逐条注明理由 |
| 未动 `RedisFlight.execute` 的产品轮询循环 | 红线「不改产品行为」；它本来就按注入时钟结算 | 产品侧仍有内联等待写法，若将来要收敛需另立票 |

## 未验证项

- 全量权威读数由出票方串行复跑；此处读数是隔离库 `br_t16_verify` 上的一次串行全量（1016 passed），库已 drop。
- 并行/共享库下的 P15-1 漂移没有复验（本次只做串行 + 隔离库）。
- 未跑 deploy / e2e / fault / soak / real 层（本票不涉及部署与真机）。
- `test_distributed_flight.py::test_waiting_is_bounded_and_reports_overload` 仍用真实时钟（wait 0.1s / poll 0.01s）验证产品循环的有界性：把它改成 ManualClock 驱动要碰产品轮询节奏，超出本票红线。
- 假时钟驱动「产品循环」的路径未覆盖：原语目前只被测试与新增用例使用，产品侧 `RedisFlight.execute` 未改为调用它。
