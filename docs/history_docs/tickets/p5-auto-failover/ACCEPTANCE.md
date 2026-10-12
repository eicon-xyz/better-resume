# P5 验收包：Redis 自动 failover（Sentinel）

> 分支 `p5/auto-failover`（基于 `main` = `4ef9f55`）。提案：`README.md`；台账：`PROBLEMS.md`（P5-1 / P5-2 / **P41**）。
> 一句话结论：**主被冻结后应用在无人干预下自己切到新主**（哨兵 `+switch-master` 为证），
> 本地收口 `verify.sh --layer all` **12 条命令全绿**。

## 1. 复跑命令

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_SMOKE_KEY=smoke-fake-key BR_SSE_HEARTBEAT_SECONDS=1

# ① 冷卷跑自动 failover 演练（起 drill profile：1 主 + 2 副本 + 3 哨兵）
docker compose --profile drill down -v
bash scripts/fault_injection_drill.sh --sentinel

# ② 本地收口（12 条命令；contract 层要求干净工作树）
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer all

# ③ 只跑本次新增的单测
cd apps/api && uv run pytest tests/test_redis_client.py tests/test_settings.py tests/test_deploy_manifest.py -q
```

## 2. 原始输出

### 2.1 冷卷自动 failover（`var/evidence/p5/06-sentinel-drill.log`）

```
PASS: docker compose --profile drill up -d --build --wait --scale api=2
== 哨兵当前主：172.20.0.2:6379
== 冻结主（docker compose pause redis）；预算 90s
PASS: 主挂了之后应用自己切到了新主（没有人工 promotion）
note: verdict=recovered
note: master_after_kill=172.20.0.9:6379
note: old_session_after_failover=200
note: worker_health=healthy
note: worker_heartbeat_on_new_master=1
note: sentinel_switch_log=1:X 28 Sep 2026 14:12:44.426 # +switch-master br-master 172.20.0.2 6379 172.20.0.9 6379
PASS: 自动 failover：无人干预的提升 + 从 kill 起算的恢复 + worker 存活
```

四条断言各自的意义：

| note | 说明 |
| --- | --- |
| `verdict=recovered` | 应用真的自愈了（不是"慢"，是"发生了"） |
| `master_after_kill=172.20.0.9` | 哨兵把主换到了另一个 IP——**提升真的发生了** |
| `+switch-master ...` | 哨兵自己的日志，不是我方脚本改的 |
| `old_session_after_failover=200` | 故障前的会话没丢（不是 401） |
| `worker_health=healthy` + 心跳在新主上 | 写路径也切过去了，不只是读 |

### 2.2 本地收口（`var/evidence/p5/07-layer-all.log`）

```
ALL PASS (12 commands) -- evidence: var/evidence/20260928T141532Z-all
```

## 3. 数字

| 项 | 值 | 对照 |
| --- | --- | --- |
| 后端 pytest | **831 passed / 0 failed / 0 skipped** | P5 之前 800（新增 31 例：缝 10 + settings 3 + manifest 3 + 演练 15） |
| scripts 层 | **61 passed** | 前 46 |
| `verify.sh --layer all` | **12 条命令全绿** | — |
| 冷卷演练 | `drill exit=0`，`verdict=recovered` | 修前连败 5 次，全是 `verdict=timeout` |
| ruff | `All checks passed!` / `243 files already formatted` | — |
| 真机调用 | **0 次** | 全程 fake 上游 |

## 4. 设计：为什么 8 个调用点不需要懂哨兵

```text
settings.config  ──►  RedisTopology.from_settings()          ← 唯一读 BR_REDIS_SENTINELS / BR_REDIS_MASTER_NAME 的地方
                          │
                          ▼
                     redis_client(source)                     ← 唯一出现 from_url / Sentinel.master_for 的地方
                          │
        ┌─────────────────┼─────────────────┬────────────────┐
        ▼                 ▼                 ▼                ▼
   identity/         jobs/queue       interview_engine   ai_resilience
   （8 个调用点全部只是 redis_client(source)，不知道"哨兵"这个概念）
```

自动切换交给 redis-py 的 `SentinelConnectionPool`：重连时重新向哨兵问主、丢弃旧连接。
因此**不需要**重建客户端、不需要业务侧探测或轮转（即被否掉的方案②）。

## 5. 未验证项（诚实清单）

- **pause 冻结的是「主不可达」，不是「主容器消失」**。这是本阶段最重要的限制：compose 的单机内嵌 DNS
  在容器退出后不再解析服务名，哨兵会反复 `Failed to resolve hostname` 并进入 TILT，而 **TILT 期间哨兵
  拒绝执行任何 failover**——所以"杀容器"无法作为哨兵演练的注入方式（连败 5 次的记录见 `PROBLEMS.md` P41）。
  生产环境的多可用区/独立 DNS 不存在这个限制，但**本仓库没有验证过**。
- **单机 compose 上的哨兵 ≠ 生产级高可用**：三个哨兵在同一台宿主、同一个 Docker 守护进程上，
  宿主一挂全挂。演练证明的是"应用侧能自动跟随主切换"，不是"整机高可用"。
- **没有做多可用区、真实网络分区下的哨兵脑裂治理**（提案 §4 已声明不做）。
- **CI 里没有跑这个演练**：`--sentinel` 属于 `drill` profile，nightly/weekly 目前不启它（提案 Q3 未决）。
- 恢复拓扑仍需整体重建：`docker compose --profile drill down -v`（redis 容器换 IP 后哨兵记的还是旧目标）。

## 6. 与提案的偏差

| 偏差 | 说明 |
| --- | --- |
| 演练注入改为 pause | 提案写的是"停主 + 等哨兵自动提升"。**杀容器**在 compose 单机 DNS 下必然失败（TILT），所以改为 pause 冻结。语义仍是"主不可达"，但**不是**"主进程消失"——记在未验证项。 |
| 副本从 1 个加到 2 个 | 单副本时哨兵在选举窗口里没有健康候选人（跑了两次才确认这条也不是根因，但保留 2 副本让选举更稳）。 |
| 哨兵参数调整 | `down-after-milliseconds` 5000→15000、`failover-timeout` 10000→30000。**事后确认这不是根因**（根因是 TILT），但更大的窗口对演练更稳，保留。 |
| 不在 scripts/ 加 wrap 脚本 | 用户要"一键拉起"，做成 `bash scripts/fault_injection_drill.sh --sentinel` 而不是另起一个脚本——仓库的单一入口哲学（`verify.sh` 同理）。 |
| AGENTS.md 由 Lead 补 | 演练拓扑命令、两个新变量、"恢复拓扑要 down -v" 的坑，都写进了 `AGENTS.md` 常用命令段。 |
