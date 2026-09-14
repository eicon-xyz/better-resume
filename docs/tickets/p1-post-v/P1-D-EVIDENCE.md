# P1-D 验收包：生产形态演练（Redis 分区 / 主从切换 / 60 分钟浸泡）

- 票据：`docs/tickets/p1-post-v/README.md` §2 P1-D；分支 `p1/realtime-asr`
- 结论：**三项全部完成**（分区 / 主从切换 / 60 分钟浸泡）；过程中发现并修掉 **1 个真 bug（P26）**，
  并纠正了 1 个探针自身缺陷（P27）。

## 1. 新增演练场景（`scripts/fault_probe.py` + `scripts/fault_injection_drill.sh`）

```bash
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20
bash scripts/fault_injection_drill.sh          # 现在含 5 个故障实验 + 浸泡
```

两者都把恢复放进 `finally`：**任何崩溃都不会把栈留在断网/从库状态**（第一版没这么做，实测崩过一次，见 P27）。

## 2. 网络分区（api↔redis 断开 20s，docker network disconnect）

| 指标 | 读数 |
| --- | --- |
| 故障窗口 | 9 次探测全 `timeout`（2s 客户端预算）、0 次错误状态码 |
| `/healthz` | **9/9 成功**（不依赖 Redis 的路径不受影响） |
| 认证读路径 | 采样为 `ReadTimeout`；**原始 curl 对照：503 + `retry-after: 5`**（P17 契约成立） |
| 恢复 | 网络恢复后首次成功 **207ms / 2200ms**（两次运行） |
| 自愈 | 无需重启任何容器 |

## 3. 主从切换（真实从库复制 → 停主 → 提升 → 接管 'redis' 名）

| 指标 | 运行 1 | 运行 2（P26 修复后） |
| --- | --- | --- |
| 复制完整性 | `link=up dbsize 11=11` | `link=up dbsize 3=3` |
| 故障窗口 | 74 ok / 1 server_error（共 75） | **91 ok / 1 server_error（共 92）** |
| 恢复 | 191ms | **109ms** |
| 切换前会话 | **200（存活）** | **200（存活）** |
| worker | **exit 1 —— 死亡（P26）** | **healthy；7 条 `worker_loop_error` 优雅降级** |
| 拓扑还原 | ✅（从库删除、主库回归） | ✅ |

## 4. P26（真 bug，已修，红-绿）

**现象**：主从切换时 worker 进程 `exit 1`，容器无重启策略 → **后台任务永久停摆**（直到人工重启）。
**根因**：`worker.serve()` 里 `beat()`（心跳写 `client.set`）位于兜底 `try` **之外**；Redis 抖动抛出的
`redis.exceptions.TimeoutError` 直接逃出循环。M6 P9 只补了阻塞读路径。
**修法**：把 `beat` 移进兜底 try（记录 + 退避，与 job 循环同一套失败处理）。
**验证**：红 → `test_serve_survives_a_redis_timeout_in_the_heartbeat`（`assert 1 >= 2` 失败）；
绿 → 全量 **695 passed / 0 failed**；真机复跑切换演练 → `worker_health=healthy` + 7 条降级日志。

## 5. 60 分钟浸泡（完成）

- 命令：`fault_probe soak --duration 3600 --wave-seconds 30 --requests 30 --concurrency 4`（**只打 /healthz + /auth/*，零供应商调用**）
- 日志：`/tmp/p1d-soak-60m.log`；JSON：`/tmp/p1d-soak-60m.json`

| 指标 | 读数 | 判读 |
| --- | --- | --- |
| 波数 / 请求 / 成功 | **120 波 / 3600 / 3600 ok** | **error_rate 0.0**，一小时零失败 |
| redis_keys 增长 | **+238**（全部是 session 键） | 浸泡每波建 2 个会话 × 120 波 ≈ 240，**设计使然**（30 天 TTL），非泄漏 |
| redis 非会话键增长 | **0** | 任务流/心跳键无累积（这是真正要看的泄漏面） |
| redis 内存增长 | **+0.1 MB** | 可忽略 |
| Postgres 连接增长 | **0** | 无连接泄漏（连接池稳定） |
| api 进程内存增长 | **+0.5 MB / 小时** | 无堆增长迹象 |

结论：V6 的 10 分钟结论在 **60 分钟**尺度上复现且更干净——除按期增长的会话键外，**没有任何资源随负载漂移**；
后台 worker 心跳、任务流、PG 连接池在整小时内保持稳定。

## 6. 未验证 / 边界（诚实清单）

1. **无自动 failover**：应用是单 `BR_REDIS_URL`，没有哨兵/多端点支持；本轮量的是"人工切换的停机时间"
   （= 提升 + 重新指向 + 容器重连，实测 ~0.1–2.2s）。自动切换需要代码改动 → 另开提案。
2. 切换瞬间存在**短暂 503 窗口**（陈旧连接池指向旧主），实测在 1 次探测内恢复。
3. 单机单实例 Redis 演练；多可用区/网络分区矩阵不在本轮。
4. 浸泡为 1 小时（V6 是 10 分钟），不是 24 小时长跑。

## 7. 复跑

```bash
cd '/root/better resume/apps/api' && export PATH="$HOME/.local/bin:$PATH"
uv run pytest tests/test_worker_health.py tests/test_fault_probe.py -q     # P26 回归 + 探针纯逻辑
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20
```
