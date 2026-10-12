# P5 实现报告：Redis 自动 failover（task-1）

> 分支 `p5/auto-failover`；写作用域：`apps/api/src/better_resume/`、`apps/api/tests/`、
> `compose.yaml`、`.env.example`、`docs/tickets/p5-auto-failover/`。
> 规格：`docs/tickets/p5-auto-failover/README.md`（用户已确认：① Sentinel；② 哨兵默认不启、归 drill profile）。
> 状态：**实现完成，等 Lead 跑冷卷演练收口**。

## 1. 交付物（改了什么）

| 文件 | 一句话 |
| --- | --- |
| `apps/api/src/better_resume/redis_client.py`（新增） | 取 Redis 客户端的**唯一缝**：`RedisTopology`（单 URL 或哨兵拓扑）+ `redis_client()`；全仓库只有这里出现 `from_url` / `Sentinel.master_for` |
| `apps/api/src/better_resume/settings/config.py` | 新增 `BR_REDIS_SENTINELS`（逗号分隔）+ `BR_REDIS_MASTER_NAME`；两者皆空 = 单 URL（行为与今天一致），只配一半 = 启动即拒并点名缺失变量 |
| `ai_resilience/distributed.py`、`identity/tickets.py`、`identity/redis_store.py`、`jobs/queue.py`、`worker.py`（×2）、`interview_engine/hot_state.py`、`interview_engine/locks.py` | 8 处 `from_url` 全部改走缝；构造参数由 `redis_url: str` 改为 `redis_source: RedisSource`（`str` 仍可传 = 单 URL） |
| `worker.py` / `main.py` / `identity/factory.py` / `interview_engine/hot_state.py` 的装配点 | 改传 `RedisTopology.from_settings(settings)`（唯一读配置的地方） |
| `compose.yaml` | `redis-replica` + `redis-sentinel-1/2/3`，全部 `profiles: ["drill"]`；api/worker 透传两个新变量（默认空） |
| `.env.example` | 两个变量名 + 一条演练命令（只写变量名，凭据纪律不变） |
| `apps/api/tests/test_redis_client.py`（新增 10 例）、`tests/test_settings.py`（+3）、`tests/test_deploy_manifest.py`（+3） | 缝的单测 + 哨兵默认不启的清单断言 |

## 2. 缝放哪、为什么这么放

- **位置**：包根新模块 `better_resume/redis_client.py`（不是 `db/`）。理由：Redis 是横跨
  `identity` / `jobs` / `interview_engine` / `ai_resilience` 四个模块的共享依赖，不属于任何单一功能模块；
  而 `db/` 在 D03 的双件套里明确是 Postgres 引擎的位置，把 Redis 塞进去反而模糊边界。
- **形态**：`RedisTopology`（值对象：`url` / `sentinels` / `master_name`）+ `redis_client(source, *, decode_responses, socket_timeout)`。
  调用点只拿到一个 `redis.asyncio.Redis`，**不感知端点，也不知道有哨兵这回事**——切换知识只有一份。
- **为什么不用「注入 client」**：8 处调用点里 6 处是「构造函数里建客户端、生命周期跟着对象」的形态，
  注入 client 要把生命周期管理推给每个装配点（7 个装配点各写一遍 close），反而把知识摊开了。
  传拓扑则保持「谁用谁建、谁建谁关」不变，且测试仍可传裸 URL（等价于今天的 `from_url`）。
- **自动切换发生在哪**：redis-py 的 `SentinelConnectionPool`。连接失败/被降级（`ReadOnlyError`）时它会
  `get_master_address()` 重新问哨兵、丢弃旧连接，所以**不需要重建客户端对象**，也不需要在业务代码里写探测/轮转
  （提案里被否掉的方案②）。
- **配置语义**：`BR_REDIS_SENTINELS` 非空才启用哨兵；只配一半时 `Settings` 直接 `ValidationError`
  （**比提案多的一条**：静默退回单 URL 会变成「切换时没人救得回来」的隐形故障，宁可起不来）。
- **与提案的偏差**：提案写「`docker compose --profile drill up -d` 一键拉起」；实探下来，
  **应用要走哨兵还得把两个变量给进去**（compose 无法按 profile 改 env），所以文档统一写成一条带变量前缀的命令：
  `BR_REDIS_SENTINELS=… BR_REDIS_MASTER_NAME=br-master docker compose --profile drill up -d`。
  普通 `docker compose up` 不启哨兵、不读这两个变量，行为与今天完全一致。

## 3. 证据（命令 + 原始数字）

| 命令 | 结果 |
| --- | --- |
| `cd apps/api && uv run ruff format` | `243 files left unchanged`（收尾那次；实现中途一次 `2 files reformatted`） |
| `uv run ruff check` | `All checks passed!` |
| `uv run pytest --junitxml=/tmp/p5-full.xml`（导出 BR_DATABASE_URL / BR_REDIS_URL） | **816 passed**，junit `{tests: 816, failures: 0, errors: 0, skipped: 0}`（其中新增 16 例） |
| 同上但不导出 BR_\* | `816 tests` / junit `{failures: 0, errors: 0, skipped: 136}`——skipped 只是「没给测试库地址」，不是本任务的跳过 |
| `uv run pytest tests/test_redis_client.py` | `{tests: 10, failures: 0}` |
| `uv run pytest tests/test_settings.py` | `{tests: 8, failures: 0}` |
| `uv run pytest tests/test_deploy_manifest.py` | `{tests: 17, failures: 0}` |
| `grep -rn from_url apps/api/src` | 只剩 `redis_client.py`（由 `test_only_the_seam_knows_how_to_connect` 长期看守） |
| `docker compose --profile drill config` | exit 0，无 warning（渲染出 3 个哨兵 + 1 个副本） |
| `docker compose config --services` | `postgres redis migrate worker api nginx`（6 个：**drill 服务不在默认集里**） |
| `docker compose --profile drill config --services` | 上面 6 个 + `redis-replica redis-sentinel-1/2/3`（10 个） |

红-绿过程（垂直切片，逐条红 → 最小实现 → 绿）：settings 变量（3 红）→ 单 URL 路径（2 红）→
哨兵 `master_for`（1 红）→ `from_settings` 解析（2 红）→ 「只许缝里 from_url」源码断言（8 个违规点红）→
compose 清单（3 红）。每个切片的红灯与转绿数字都在本次会话的运行记录里。
其中「`SentinelConnectionPool` 服务名/主从标记」与「坏地址报错」两组断言在写下时就已绿（属同一实现的回归钉子），
不算独立切片，这里如实标注。

## 4. 冷卷演练怎么跑、期望看到什么（**由 Lead 在收口时执行**）

```bash
cd '/root/better resume'
export BR_REDIS_SENTINELS=redis://redis-sentinel-1:26379,redis://redis-sentinel-2:26379,redis://redis-sentinel-3:26379
export BR_REDIS_MASTER_NAME=br-master
docker compose --profile drill up -d --build --wait --scale api=2

# 0) 确认哨兵真的起来了、配置落盘正确（P5-1 的遗留验证点）
docker compose --profile drill exec redis-sentinel-1 head -20 /tmp/sentinel.conf
docker compose --profile drill exec redis-sentinel-1 redis-cli -p 26379 sentinel master br-master | head -20
#    期望：flags master、num-other-sentinels 2、slaves 里能看到 redis-replica

# 1) 停主（记录时刻，口径 = 从这一刻到「应用首次成功」）
docker compose --profile drill kill redis
# 2) 期望 ≤ ~5s 判死（down-after 5s）+ 选举（failover-timeout 10s 是上限，不是耗时）
docker compose --profile drill exec redis-sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name br-master
#    期望：IP 变成 redis-replica 容器的地址；哨兵日志有 +switch-master br-master <old> 6379 <new> 6379
# 3) 应用自愈（两个 api 实例都不重启）
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/healthz          # 200（只证明进程活着）
docker compose --profile drill exec redis-replica redis-cli exists br:jobs:health # 1 = worker 心跳写到了新主上
docker compose --profile drill ps worker                                          # healthy（P26：不允许 exit 1）
```

期望的语义：切换窗口内依赖 Redis 的路径**短暂 503 + Retry-After**（P17 不变），窗口过后自动恢复 200，
**不需要人工 promotion、不需要重启 api/worker**；`num-other-sentinels=2` 说明 quorum=2 真的生效。

口径与坑：

- 判死阈值是 `sentinel down-after-milliseconds br-master 5000`；「应用首次成功」必须从 `kill` 那一瞬开始量，
  且探针别把 503 当结束（V6 教训：探针超时会截断这类测量）。
- **恢复拓扑**：单机 compose 上 `redis` 重新拉起会拿到新 IP，而哨兵是按解析后的 IP 记住监控目标的
  → 同一套栈上做第二遍会读到旧 IP。要重跑就整体重建（`docker compose --profile drill down -v` 再 up），
  或 `sentinel reset br-master` + `up -d --force-recreate redis redis-replica`。
- 哨兵模式下 `BR_REDIS_URL` **不被使用**（端点由哨兵给出）；它不是备用端点。
- 单机 compose 上的哨兵 ≠ 生产级多可用区（提案 §4 明确不做脑裂治理）。

## 5. 未验证项（诚实清单）

1. **没对着真哨兵跑过任何一次切换**：哨兵路径的 hermetic 证据只到「客户端由 `Sentinel.master_for` 产出 +
   连接池是 `SentinelConnectionPool`（重连会重新问主）」。真切换、真提升、真自愈 = 上面的演练，未执行。
2. **drill 栈没起过**：哨兵配置由容器内 `printf "$SENTINEL_CONF" > /tmp/sentinel.conf` 落盘；
   `docker compose config` 已通过（`$$` 转义后无 warning），但**容器内实际落盘内容未验证**（演练第 0 步）。
3. 冷卷端到端（停主 → 自动提升 → 应用自愈 → worker 存活 → 会话不丢）未跑。
4. `scripts/fault_injection_drill.sh` 与 `fault_probe.py --scenario redis-failover` **仍是手工提升路径**
   （不在本任务写作用域）：提案 §5 那条「演练脚本换真实自愈路径」尚未做。
5. `AGENTS.md` / `docs/HANDOFF.md` 未更新（写作用域外）：需要补「哨兵归 drill profile」+ 新变量 + 演练命令。
6. `verify.sh --layer fault` / `--layer real` 未跑（不属于本任务口径）。
7. 真机供应商调用：0 次（本任务不涉及）。

## 6. 交给 Lead 的事

- **AGENTS.md**：「部署」行 + 「环境准备」坑位补 P5 一条（drill profile、两个变量、演练命令、恢复拓扑的坑）。
- **演练脚本改造**：`fault_probe.py` / `fault_injection_drill.sh` 的 `redis-failover` 去掉手工 promotion，
  改成「kill 主 → 等 `+switch-master` → 量应用首次成功耗时 → 断言 worker 存活 + 会话不丢」。
- **拟定验收口径**：816 全绿（本报告 §3）+ `docker compose --profile drill config` 通过 + 演练原始输出。
- **问题台账**：`docs/tickets/p5-auto-failover/PROBLEMS.md`（P5-1 compose 变量插值坑）。
