# M6-T1 — Redis 分布式锁（题级锁接缝的第二个实现）

- blocking：M5
- 纪律：先写失败测试（红），再实现（绿）；Redis 用真实例（本机 6379 / compose），不 mock 内部模块

## 目标

M2 的题级锁是进程内 `asyncio.Lock`（`QuestionLockRegistry`）。多实例下它保护不了同题并发，
M6 把同一接缝的第二个实现接上：**Redis 锁**，带 owner token 与租约续期，异常路径必须释放。

## 交付物

- `interview_engine/locks.py` 扩展：保持 `QuestionLockRegistry` 的签名（`acquire(session, question)`），
  新增 `RedisQuestionLockRegistry`（同一个 Protocol），实现要点：
  - `SET key token NX PX ttl` 获取；失败则短轮询重试直到超时（明确超时错误语义）
  - 后台任务按 `ttl/2` 续租（用注入时钟，测试零真实等待）；释放时校验 token（**不删别人的锁**）
  - `release` 幂等；进程崩溃后锁靠 TTL 自动过期（不引入 Redlock，单实例 Redis 语义足够）
- `settings/config.py`：`lock_backend: Literal["memory","redis"] = "memory"`、`lock_ttl_seconds`、
  `lock_wait_seconds`
- `main.py`：按 settings 构造锁注册表（`app.state.question_locks`）
- 测试：`tests/test_distributed_lock.py`（≥10 例，真 Redis + 假时钟）

## 测试

| 用例 | 断言 |
| --- | --- |
| 互斥 | 两个并发 `async with acquire`（同一题）串行执行（观察进入/离开顺序） |
| 不同题不互斥 | 并发执行时间重叠 |
| TTL 过期可抢 | 假时钟推进超过 TTL 且不续租（模拟实例崩溃）→ 另一持有者获得锁 |
| 自动续租 | 长任务（推进 TTL×2）仍独占，无中途失效 |
| token 校验 | A 的锁被 TTL 顶掉后，B 持有锁时 A 释放不会误删 B 的锁 |
| 等待超时 | 一直抢不到 → 抛明确错误（不是无限等） |
| 异常路径释放 | 持锁体抛异常 → 锁被释放（后续可获取） |
| 取消安全 | 持锁期间任务被取消 → 释放且无残留后台任务 |
| 后端切换 | settings=memory 时行为与 M2 完全一致（回归） |
| 压测小样 | 50 个并发同题请求 → 只有一个真正进入临界区（计数断言） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_distributed_lock.py` | 全绿（Redis 不可达时 skip，不静默通过） |
| 回归 | 全量测试在 `memory` 与 `redis` 两种后端下都绿 |

## 不做

- 不做 Redlock/多 Redis 实例；不做锁的可重入语义；不做跨进程锁的公平队列。

