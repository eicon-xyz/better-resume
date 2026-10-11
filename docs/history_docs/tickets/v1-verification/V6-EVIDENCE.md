# V6 证据：浸泡 + 故障注入（不需要凭据）

- 时间：2026-09-14（CST）；栈：compose `nginx + 2×api + worker + postgres + redis + fake-llm`
- 命令：`bash scripts/fault_injection_drill.sh --quick`（故障三连 + 120s 浸泡，用来验证脚本与语义）
  与 `uv run python -m scripts.fault_probe soak --duration 600 ...`（正式浸泡，见 §4）
- 观察方式：全部经 nginx（客户端视角），注入用 `docker pause/restart/stop/start`；探针 2s 超时，
  所以"超时"是**客户端等到 2s 还没答**，不是 nginx 的 60s。

## 1. redis-pause（Redis 冻结 20s）

```
== pausing redis for 20.0s (docker pause)
fault window: {"timeout": 10}
recovery: 2315 ms after the fault ended
total=10 ok_during_fault=0
PASS
```

读法：`GET /healthz`（不碰 Redis）全程 200，而**创建会话**全部 2s 超时——正好证明"API 进程活着，
依赖坏了"；解冻后 2.3s 内首个请求成功。**没有 500 泛滥**：M3 的限流/韧性中间件不会把基础设施故障
翻译成 5xx 乱码。

## 2. redis-restart（会话存在 Redis，必须真的掉线）

```
== restarting redis (sessions live there: expect logouts)
old cookie after restart: 503 (401 = session really gone)
fault window: {"ok": 34, "server_error": 1}
recovery: 144 ms after the fault ended
```

- **诚实结论**：重启 Redis 会清掉会话，客户端必须重新登录。这是设计（D11 会话存 Redis），
  文档里写清楚，不假装"无状态"。
- **503 而不是 401 是修出来的**：第一次跑是 **500**（未处理异常），见 `PROBLEMS.md` P17。
  语义修正为"**问不到 Redis = 503 + Retry-After（现在别试）**；查不到会话 = 401（请重新登录）"。
  修复后重启窗口内的 `server_error` 只剩 1 个（重启瞬间的连接拒绝），其余请求正常。

## 3. worker-crash（拿着任务死掉的消费者，任务不能丢）

```
queued report.summary for ed86233e-… (worker stopped)
v6-claimed ['LtKhQ1imYP4T0ibR']
pending before restart: 1
pending after recovery: 0
worker restart -> summary written: 59.3s
summary: '整体结构清晰，深度尚可；建议用数据说明取舍与结果。'
PASS
```

读法：一个一次性容器以 `v6-crash-sim` 身份把任务领走就退出（= 崩溃），`XPENDING=1`；
worker 起来后按 `min_idle_ms=60_000` 通过 **XPENDING+XCLAIM 接管**，59.3s 写出总结、`XPENDING` 归零。
**59.3s ≈ 60s 的接管阈值**——这个数字本身就是"崩溃恢复最坏等待时间"的证据，不美化。

## 4. 浸泡（10 分钟，采样波）

完整 JSON：`/tmp/v6-soak-clean.json`（每 30s 一波，30 请求/波，并发 4）。

```json
{
  "waves": 20, "total": 600, "ok": 600, "failures": 0, "error_rate": 0.0,
  "kinds": {"ok": 600},
  "redis_keys_growth": 42, "redis_sessions_growth": 40, "redis_other_keys_growth": 2,
  "redis_memory_mb_growth": 0.01, "pg_connections_growth": 0, "api_memory_mb_growth": 6.2
}
```

**600 请求 0 失败**（10 分钟）；键增长 42 个里 40 个是探针自己的 2 次登录/波（预期），
**非会话键只涨 2 个**（队列 status/dedupe 的短 TTL 键），Postgres 连接数不变，Redis 内存 +0.01MB，
API 常驻内存 +6.2MB（10 分钟内的分配噪声量级，不足以判定泄漏，也未观察到单调上升）。

**口径**：`redis_sessions` 是探针自己登录产生的键（30 天 TTL，属**预期增长**）；
真正看泄漏的是 `redis_other_keys_growth`（非会话键）、`redis_memory_mb_growth`、
`pg_connections_growth`、`api_memory_mb_growth`。探针每波只登录 2 次，其余读 `/auth/me`，
避免"探针自己把 Redis 撑大"这种自欺欺人的数字。

## 5. 结论

| 问题 | 结论 |
| --- | --- |
| Redis 挂了会怎样？ | 只影响依赖它的接口（会话/锁/热层/队列）；健康检查仍 200；解冻后秒级自愈 |
| 会话会丢吗？ | 会（存在 Redis），且现在以 503 表达"暂时问不到"，不是假装未登录（P17） |
| worker 崩了任务会丢吗？ | 不会；最多等 `min_idle_ms`（实测 59.3s）后被接管并完成 |
| 跑 10 分钟会涨吗？ | 见 §4 汇总（非会话键与内存的增长是否在噪声范围内） |
| 没验的是什么？ | 网络分区（tc netem）、多节点故障、Redis 集群；本机单节点做不到，已列入未验证项 |
