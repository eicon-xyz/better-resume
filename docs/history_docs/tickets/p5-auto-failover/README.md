# P5 提案：Redis 自动 failover（从「人工演练」到「系统自愈」）

> 依据：P1-D 已完成**手动** failover 演练（手工停主 → 手工提升副本 → 手工恢复拓扑，恢复 109ms、worker 存活）；
> `docs/tickets/p1-post-v/README.md:97` 把「Redis 主从 + 手动 failover」记为已验证，把「自动 failover」列为候选；
> P4 收口后 nightly / weekly 已能真跑，具备了把演练接进 CI 的条件。
> 状态：**提案，等用户确认后动工**。

## 1. 现状盘点（实测）

- `BR_REDIS_URL` 是**单个 URL**（`settings/config.py:119`），**8 处** `from_url` 直接用它：
  `ai_resilience/distributed.py:99`、`identity/tickets.py:66`、`identity/redis_store.py:25`、
  `worker.py:101` / `worker.py:148`、`jobs/queue.py:52`、`interview_engine/hot_state.py:84`、`interview_engine/locks.py:94`。
- `compose.yaml` 里只有一个 `redis:7-alpine`（无副本、无哨兵）。
- 今天的能力：主节点挂了 → 所有依赖 Redis 的路径回 503（P17 语义正确，实测两副本在恢复后 >24s 仍 503），
  **但要人来把它救回来**。那 109ms 是「人手操作之后」的恢复，不是系统自愈。

## 2. 目标

1. 主节点不可用时，应用**无需人工**切到可用节点并恢复服务；切换过程中对调用方的语义仍是 P17 的 503 + Retry-After（不假装成功）。
2. 演练脚本把「手工停主 / 手工提升 / 手工恢复」换成**真实的自愈路径**，并在 CI 里跑。
3. **8 处调用点不应各自学会 failover**——把它们收到一个缝后面。

## 3. 方案分叉（需要你拍板）

| | 方案 | 代价 | 备注 |
| --- | --- | --- | --- |
| **①** | **Redis Sentinel**（3 sentinel + 1 replica；应用用 `redis.asyncio.Sentinel.master_for()`） | compose 加 3 个 sentinel 容器；8 处调用点改成一个「取客户端」的缝 | redis-py 原生支持；兼容 Redis 6.0 下限（M6 P7） |
| **②** | 自研多端点（URL 列表 + 健康探测 + 轮转） | 要自己写探测 / 切换 / 一致性，且写操作在旧主上仍可能成功（脑裂） | 不引 sentinel，但把分布式难题搬进业务代码 |
| **③** | 保持手动（只把演练自动化） | 0 代码改动 | 与「生产形态演练」的初衷相悖 |

**推荐 ①**：这是 Redis 的标准答案，而且能把「切哪个节点」从业务代码里彻底移出去（一个缝解决 8 个调用点）。

## 4. 不做

- 不做多可用区 / 真实网络分区下的哨兵脑裂治理（超出单机 compose 的形态，D07）。
- 不动 Postgres 侧。
- 不引入第三方 Redis 代理（twemproxy / envoy）。
- 不改业务语义（503 仍然是 503）。

## 5. 交付物

- `settings/config.py`：新增 `BR_REDIS_SENTINELS`（逗号分隔）+ `BR_REDIS_MASTER_NAME`；
  **两者都为空时保持今天的单 URL 行为**（向后兼容，本地 / CI 默认不变）。
- 一个 `redis_client()` 缝（位置待定：`db/` 还是新模块），8 处调用点改为经它取客户端。
- `compose.yaml`：`redis-replica` + `redis-sentinel` ×3，**归属 `drill` profile**（默认 `docker compose up` 不启；
  `docker compose --profile drill up -d` 一键拉起），并在 `AGENTS.md` / 票据里写清这条命令。
- `scripts/fault_injection_drill.sh`：`redis-failover` 实验改为**停主 + 等哨兵自动提升 + 断言应用自愈**，不再手工 promotion。
- `docs/tickets/p5-auto-failover/PROBLEMS.md` + `ACCEPTANCE.md`。

## 6. 测试与验收口径

- **单测**：假时钟 + fake sentinel（只 mock 系统边界）验证「主挂了 → 取到新主 → 重建客户端」；断言不依赖真 Redis。
- **演练**：新场景（如 `--scenario redis-failover --auto`）在**冷卷** compose 上真跑：停主 → 记录「应用首次成功」耗时 → 断言 worker 存活 + 会话不丢。
- **不回退**：`verify.sh --layer all` 12 条命令全绿；`--layer fault` 全绿。
- **诚实清单**：明确写「单机 compose 上的哨兵 ≠ 生产级多可用区」。

## 7. 预估

- 代码：settings + 一个新缝 + 8 处调用点 + 测试；1–2 天。
- compose：3 sentinel + 1 replica，本地起栈 +约 10s。
- **真机调用：0 次**。

## 8. 需要你决定的问题

- ~~Q1：选哪个方案？~~ → **已确认：① Sentinel**（2026-09-24）。
- ~~Q2：sentinel 进默认 compose 还是 profile？~~ → **已确认：默认不启**，放 `drill` profile；演练时 `docker compose --profile drill up -d` 一键拉起。要写进文档与票据。
- **Q3**：nightly 里也跑自动 failover 演练吗？（weekly 已有 5 实验 + 浸泡；nightly 目前只跑 deploy + fault --quick）
- **Q4**：`docs/HANDOFF.md` §2 还写着旧流程（阶段提案制）——本阶段收口时一并更新？
