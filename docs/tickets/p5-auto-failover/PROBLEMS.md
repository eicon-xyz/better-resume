- **遗留**：容器内**实际落盘内容**仍未验证（本机没起 drill 栈），演练第一步用
  `docker compose --profile drill exec redis-sentinel-1 head -20 /tmp/sentinel.conf` 确认。


## P5-3 / P41 冷卷演练连败五次：compose 单机 DNS 让哨兵进 TILT，failover 永不发生

**这是本阶段最值钱的一条，因为它把「我以为的原因」和「真正的原因」分开记了。**

### 现象（五次失败，收敛过程）

| 第几次 | 注入方式 | 结果 | 我当时的假设 |
| --- | --- | --- | --- |
| 1 | `docker compose kill redis` | `verdict=timeout`、`master_after_kill` 未变、`switch_log=none` | 副本被同时判下线 → 加 `down-after` |
| 2 | 同上 + `down-after` 5000→15000 | 同上（选举完成但选不出副本） | 单副本拓扑限制 → 加第二个副本 |
| 3 | 同上 + 两个副本 | 同上；日志出现 `Failed to resolve hostname 'redis'` + `+tilt` | DNS 失效 → 改杀进程 |
| 4 | `redis-cli shutdown nosave` | 同上；容器 Exited，DNS 照样失效 | 需要静态 IP？→ 先试删 `resolve-hostnames` |
| 5 | 删掉 `resolve-hostnames yes` | **栈都起不来**（哨兵 exit 1） | 走错方向，回滚 |

前两次假设（副本数、参数）**都是错的**——加副本、调参数都不解决，因为 failover 根本没被触发。

### 真根因（一条完整因果链）

```text
kill 容器 / shutdown 进程
  → redis 容器 Exited（没有 restart policy）
  → compose 的单机内嵌 DNS 不再解析服务名 `redis`
  → 哨兵每 5 秒一次 "Failed to resolve hostname 'redis'"
  → 哨兵进入 TILT 模式（它认为自己无法可靠履职）
  → **TILT 期间哨兵拒绝执行任何 failover**
  → master_after_kill 始终等于原主，verdict=timeout
```

关键证据：`docker compose exec redis-sentinel-1 getent hosts redis` 在主停后**返回空**；
3 分钟内哨兵日志里 `+tilt mode entered` 出现 **8 次**。

### 修法

**换注入方式，而不是继续调参数**：`docker compose pause redis`——
容器还在、名字仍可解析、IP 不变，只是所有连接超时。哨兵于是能正常走 `sdown → odown → 提升副本`。
这也正是仓库既有的 `redis-pause` 故障语义（fault 1/5 用的就是它）。

配套两处：
1. `restore_drill_topology()` 补 `docker compose unpause redis`——**恢复动作必须覆盖注入方式**，
   否则演练结束栈永远停在冻结态（V6 教训）。
2. `heartbeat_on_new_master()` 改为同时查 `redis-replica` 与 `redis-replica-2`：drill 拓扑有两个副本，
   哨兵提升哪个不确定，只查一个会把「提升了 replica-2」误报成 0——那是探针在说谎。

### 证据

- **红**：`var/evidence/p5/01..05-sentinel-drill.log`（五次，逐次记录 verdict / master_after_kill / switch_log /
  TILT 次数 / DNS 解析结果）
- **绿**：`var/evidence/p5/06-sentinel-drill.log`——`drill exit=0`、`verdict=recovered`、
  `master_after_kill=172.20.0.9:6379`（换了主）、`+switch-master br-master 172.20.0.2 6379 172.20.0.9 6379`、
  `old_session_after_failover=200`（会话没丢）、`worker_health=healthy`、`worker_heartbeat_on_new_master=1`
- **诚实说明**：pause 冻结的是「主不可达」，不是「主容器消失」。compose 的单机 DNS 决定了
  后者无法作为哨兵演练的注入方式——这条限制本身写进 ACCEPTANCE 的未验证项。

## P5-2 哨兵配置文件不能只读挂载（设计约束，非缺陷）

- **现象**：最初想用 compose configs/只读挂载把 `sentinel.conf` 塞进去。
- **根因**：哨兵运行时会重写自己的配置文件（记录已知哨兵/副本/纪元），只读文件会让它启动失败。
- **修法**：启动命令先 `printf` 落到容器内可写路径 `/tmp/sentinel.conf`，再 `exec redis-sentinel`。
  因此三个哨兵共用同一份模板内容是安全的（各自写各自的容器内副本）。