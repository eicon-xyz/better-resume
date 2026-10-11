# P7 提案：限流状态迁到 Redis（多副本共享同一配额）+ 显式降级语义

> 依据：P1-B 首次量化了「进程内限流 × N 副本 = 单身份实际配额 ×N」（`docs/perf/M6-capacity.md` §2.7，
> 标定后 c=16 → 8 ok + 8 rate_limited = 2 副本 × burst 4，与模型分毫不差）；
> `ai_resilience/ratelimit.py` 的模块注释自己写着「Redis-backed limits arrive with M6 behind the same
> Bucket/check seam」——本提案就是兑现这条缝。
> 状态：**提案，等用户确认（Q1–Q5）后动工**。

## 1. 现状盘点（实测，行号可查）

| 事实 | 位置 |
| --- | --- |
| 桶是**进程内字典**：`dict[(Bucket, identity)] → TokenBucket`，懒淘汰 idle（上限 10 000 身份） | `ai_resilience/ratelimit.py:65-125` |
| 桶选择：method+path → `AI_CALL / ANSWER / HEAVY / READ / GENERAL` | `http/ratelimit.py:36-51` |
| 身份：session cookie 的 sha256 前 16 位（`session:…`），匿名回退 `ip:…` | `http/ratelimit.py:104-109` |
| 中间件自己出错 → **fail-open**（记 `ratelimit_failed_open` 日志，**不是** 500） | `http/ratelimit.py:69-71` |
| 429 语义：`Retry-After` + `X-RateLimit-Bucket` + `X-RateLimit-Remaining: 0` + body `{detail,bucket,retry_after}`（成功路径另带 `X-RateLimit-Limit`） | `http/ratelimit.py:73-94` |
| 额度：`ai_call 2/s`、`answer 2/s`、`heavy 2/s`、`general 20/s`、`read 15/s`、burst ×2（P1-B 标定） | `settings/config.py:85-96` |
| `RateLimiter.check()` 是**同步**方法，全仓只有 3 个调用点：HTTP 中间件、`main.py` 装配、`scripts/resilience_smoke.py` | grep 实测 |
| Redis 缝已存在：`redis_client(RedisSource)`（含哨兵自动 failover），Lua 先例在 `identity/tickets.py:15-19`（2 行脚本 + `eval`）、`ai_resilience/distributed.py:38-51` | `redis_client.py` |
| **时钟口径**：`SystemClock.now() = time.monotonic()`——**跨进程不可比**，不能直接用于共享状态的时间运算 | `ai_resilience/clock.py:19-22` |
| 现有测试：单测 **7** 例（ManualClock）+ HTTP **8** 例（TestClient，断言头/body/白名单/身份隔离/fail-open） | `tests/ai_resilience/test_ratelimit.py`、`tests/test_ratelimit_http.py` |

## 2. 目标

1. 受限桶的状态放 Redis，**N 个副本共享同一份配额**（不是每副本一份）。
2. **显式定义** Redis 不可用时的降级语义，并写进 `SKILL.md` + `DECISIONS.md`（续编 **D19**）——今天这条语义只活在中间件的一个 `except` 里，没有任何文档描述它对多副本意味着什么。
3. 对外语义**逐条不变**：`X-Instance-Id` 照旧、429 映射照旧、白名单照旧、身份哈希照旧（≥ 回归测试钉住）。
4. 令牌恢复用**注入时钟**验证（不写真实 sleep 断言），Redis 只在边界上被 mock。

## 3. 方案

### 3.1 缝的形状：`BucketStore` 协议（保持 `check()` 是唯一对外动词）

```python
class BucketStore(Protocol):
    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]: ...
    async def aclose(self) -> None: ...

# ai_resilience/ratelimit.py：RateLimiter.check 改为 async，内部委托给 store
#   InProcessBucketStore  = 今天 TokenBucket 的字典（降级兜底也用它）
#   RedisBucketStore      = 新增 ai_resilience/redis_buckets.py（Lua）
```

`check()` 变 async 是**唯一的破坏性改动**：调用点 3 处（中间件 `await`、`main.py` 装配、smoke 脚本）+
7 个已有单测。这是必要代价——Redis 是 async 的，把同步 API 保留成假象会污染调用方。

### 3.2 Lua：令牌桶（沿用现有 TokenBucket 公式，1 次往返原子完成）

键 `br:rl:{bucket}:{identity}`，hash 存 `tokens` / `ts_ms`，TTL = `max(60s, 3 × 满桶恢复时间)`：

```lua
-- KEYS[1]=bucket 键  ARGV: now_ms, rate_per_s, capacity, ttl_ms
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens, ts = tonumber(state[1]), tonumber(state[2])
local now, rate, cap = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
if tokens == nil then tokens, ts = cap, now end
tokens = math.min(cap, tokens + math.max(0, now - ts) / 1000 * rate)   -- 负 elapsed 钳到 0（同 TokenBucket）
local allowed, retry = 0, 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 else retry = (1 - tokens) / rate end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], ARGV[4])
return { allowed, tostring(retry), tostring(math.floor(tokens + 1e-9)) }  -- Lua 会把浮点截成整数，必须转字符串
```

- 用 **`eval`**（每次带脚本）而不是 `EVALSHA`+`SCRIPT LOAD`：与 `identity/tickets.py` 的先例一致，
  没有脚本缓存生命周期（`NOSCRIPT` 回退）要管；脚本 ~400B，一次往返的成本差异可忽略。
- TTL 过期即是今天的「懒淘汰 idle 桶」——`max_identities` 那套在 Redis 侧由 TTL 承担。

### 3.3 时间基线（必须拍板的技术点）

`SystemClock` 是 **monotonic**，两个容器的 monotonic 起点不同 → 直接把 `clock.now()` 传进 Lua，
会出现 `now - ts < 0`（一个副本永远不恢复令牌）。备选：

| | 方案 | 优点 | 代价 |
| --- | --- | --- | --- |
| **①** | **应用侧 wall-clock（`time.time()*1000`）作为新缝 `WallClock`，Lua 只做算术** | 时间走注入时钟（与仓库纪律一致）→ **假时钟可确定性验证令牌恢复**；Redis 路径与进程内路径公式完全一致（降级时行为不变） | 跨副本 wall-clock skew 直接进入配额（本机同宿主 = 0；一般容器同宿主/同 NTP，百毫秒级 → 2/s 下 ≈0.2 token） |
| ② | Lua 内 `redis.call('TIME')` | 时间源唯一、无 skew | 时间不可注入 → 令牌恢复只能用真实 sleep 测（违反本仓测试纪律），且与进程内路径的时钟语义分叉 |

**推荐 ①**：仓库纪律（`SKILL.md` 不变量：时间全部走注入的 Clock）与「降级后行为与今天一致」这两条，
比毫秒级 skew 更重要；skew 的影响有界（≤ 每百毫秒 0.2 token @2/s），写进文档与诚实清单。

### 3.4 哪些桶共享（Q2）

| | 范围 | 理由 |
| --- | --- | --- |
| **①（推荐）** | 只共享**供应商成本桶**：`AI_CALL / ANSWER / HEAVY` | 这三桶限的是**外部配额**（供应商 token 与钱），多副本必须共享；`GENERAL/READ` 限的是**我们自己的容量**——副本变多，我们自己的容量也变多，**按副本限才是对的**；顺带让 GET 快路径（p50 4–10ms）不增加一次 Redis 往返 |
| ② | 五个桶全部共享 | 心智模型统一（"所有配额都是全局的"）；代价：每请求 +1 往返，且 general/read 的语义从"每副本容量"变成"全局配额"（需重新标定 15/20 是否够） |

### 3.5 降级语义（Q1，三选一 + 一个变体）

| | 方案 | 可用性 | 供应商保护 | 与现状的关系 | 复杂度 |
| --- | --- | --- | --- | --- | --- |
| A | **fail-open 全放行**（Redis 挂了就不限流） | 最好 | 无（只剩熔断/舱壁/超时兜底） | 比今天更松 | 最低 |
| B | **fail-closed**（受限端点全 503 + Retry-After） | 最差：Redis 抖动 = 全站不可用 | 最好 | 与 `http` SKILL 不变量 3（限流 fail-open）**直接冲突**，必须显式改不变量 | 低 |
| C | **降级到进程内桶**（本地桶照常按 rate 限，配额暂时 ×N）+ **显式可观测**（结构化 warning `ratelimit_degraded`、`/resilience/stats` 计数、响应头 `X-RateLimit-Scope: instance`）+ **冷却窗口**（首次失败后 N 秒内不再尝试 Redis） | 好（与今天同） | 退化为今天的水平（×N，**不是无限制**） | **最坏情况 = 今天已发布的语义，不引入新风险** | 中 |
| D | **按上次快照拒绝**（本地镜像继续判，恢复前只减不增） | 差：令牌耗尽后等价于 fail-closed | 好 | 新语义 | 最高（镜像 + 恢复同步 + 谁赢的规则） |

**推荐 C**，理由三条：

1. **它的最坏情况就是今天的基线**（每副本一份配额）。A 比今天更松，B/D 比今天更严——而"降级"的定义应该是
   "退回上一个已知good状态"，不是"切换到一个从未验证过的新语义"。
2. **限流不是正确性**（`http/ratelimit.py` 注释原话）：把 Redis 抖动升级成 503，等于用可用性去换一个
   **本来就不精确**的配额（D 的"快照"也一样：跨副本快照不同步，它并不比 C 更准，只是更严）。
3. C 的关键增量是**显式**：日志 + 计数 + 响应头 + 冷却窗口 + 演练断言。今天的问题是这条路径不可观测，
   而不是它太松。

**变体 C'（若你要更强的供应商保护）**：按桶分层——`AI_CALL/ANSWER/HEAVY`（花钱桶）在 Redis 不可用时
**fail-closed 429**（不是 503：语义是"配额暂时不可用 → 保守拒绝"，且 429 比 503 更贴近真实原因），
`GENERAL/READ` 保持 fail-open。代价：多一条语义分叉 + 需要你在 §8 里认可"花钱桶在 Redis 抖动期间不可用"。

### 3.6 配置（`BR_RATE_LIMIT__*`）

| 设置 | 默认 | 说明 |
| --- | --- | --- |
| `backend` | `memory` | `memory`（今天行为，本地/CI 默认）\| `redis`；compose 设 `redis`——与 `lock_backend`/`hot_state_backend` 同一模式 |
| `shared_buckets` | `ai_call,answer,heavy` | Q2 的选择；仅 `backend=redis` 时生效 |
| `redis_socket_timeout_ms` | `50` | 单次 `eval` 的硬上限（抖动时不给请求叠延迟） |
| `degraded_cooldown_seconds` | `30` | 首次失败后不再尝试 Redis 的窗口（避免每个请求都吃一次超时） |

`compose.yaml` 加 `BR_RATE_LIMIT__BACKEND: ${BR_RATE_LIMIT__BACKEND:-redis}`（其余留默认）；
`.env.example` 只列变量名 + 注释；`BR_RATE_LIMIT__*` 是嵌套（`__`）——`rate_limit` 已经是 `Settings` 的嵌套块。

## 4. 这会**收紧**配额（重要的行为变化，Q3）

迁移到共享配额后，2 副本场景下 `AI_CALL` 的实际能力从 **4/s、burst 8**（每副本 2/s、burst 4）变成
**2/s、burst 4**——即 §2.7 里"8 并发仍 4× 余量"这句话需要改写成"4 并发、2× 余量"。
这是**配额的本意**（一个身份就该只有一份配额），但它会让真机多身份并发（P1-B 的 24 并发）**更难**：
24 并发是 3 进程 × 8 身份聚合出来的，单身份仍受 4 并发限制，所以 24 并发本身不受影响；受影响的是
**单个身份跨副本刷**的场景（那正是"放大 N 倍"被堵掉的地方）。

## 5. 不做

- 不做全局限流（跨身份的总额度/全局 QPS 上限）——那是另一件事，需要先有容量结论。
- 不做按用户等级的差异化配额、不做计费式配额、不做"预留令牌"。
- 不改 `ai_resilience` 的韧性链（熔断/舱壁/超时/单飞）语义，不动 Postgres。
- 不引入第三方限流库（redis-cell / GCRA 库）——D04/D17 依赖纪律；GCRA 作为等价实现**评估后不采用**：
  它与现有 `TokenBucket` 公式不同，会导致"降级路径与主路径行为不一致"。
- 不做 Redis 侧每身份键数上限（今天有 `max_identities=10 000`）——靠 TTL；这条留进诚实清单。

## 6. 交付物

| 文件 | 改动 |
| --- | --- |
| `ai_resilience/ratelimit.py` | `check` → async；`BucketStore` 协议 + `InProcessBucketStore`；降级决策与冷却窗口；指标 `rate_limit_degraded` |
| `ai_resilience/redis_buckets.py`（新） | Lua 脚本 + `RedisBucketStore`（走 `redis_client()` 缝，哨兵可用时自动继承 failover） |
| `ai_resilience/clock.py` | 新增 wall-clock 缝（`now_ms()`）：`SystemWallClock` + `ManualWallClock`（测试用） |
| `http/ratelimit.py` | `await`；响应头加 `X-RateLimit-Scope: shared\|instance`；429 语义不变 |
| `main.py` | 按 settings 装配 store；lifespan `finally` 里 `aclose()` |
| `settings/config.py` | §3.6 的 4 个字段 |
| `compose.yaml` / `.env.example` | 变量透传与变量名清单 |
| `skills/modules/ai_resilience/SKILL.md` | 新不变量：限流降级语义 + 时钟口径（monotonic 不可跨进程） |
| `skills/modules/http/SKILL.md` | 不变量 3 精确化：fail-open 的准确含义 = 降级到进程内桶（不是无限放行） |
| `docs/DECISIONS.md` | **D19**：限流状态放 Redis（共享配额）+ 降级语义（Q1 的结论） |
| `docs/perf/M6-capacity.md` §2.7 | 配额口径更新（跨副本不再 ×N；"8 并发"→"4 并发"）+ 迁移后压测数据 |
| `scripts/resilience_smoke.py` | `await check(...)` |
| `scripts/compose_smoke.sh` / `scripts/kill_instance_drill.sh` | 新增断言：跨副本共享配额（见 §7） |
| `docs/tickets/p7-shared-rate-limit/` | `ACCEPTANCE.md` + `EVIDENCE.md` +（若有）`PROBLEMS.md` |
| 收口时检查 | 其它文档里的「D01–D18」范围引用：`AGENTS.md`、`docs/agents/domain.md`、`docs/HANDOFF.md` 已在本票改；**`docs/ARCHITECTURE-MAP.md` 在 `docs/architecture-map` 分支上**，若它先合入，本票合入时要一并把它的范围改成 D01–D19 |

## 7. 测试与验收口径

**测试缝（只 mock Redis 边界）**：

- 缝 A：`BucketStore` 的 fake（记录入参、可注入 `RedisError`）→ 决策透传 / 降级 / 冷却 / 恢复，全用假时钟。
- 缝 B：真 Redis 集成（不可达则 `skip`，与 `tests/test_distributed_flight.py` 同规矩）→ 两实例共享配额、
  原子性（并发 100 次取只放行 capacity 次）、TTL 过期、**注入假 wall-clock 推进后的令牌恢复**。
- 缝 C：HTTP 层（沿用 `test_ratelimit_http.py` 的 `tight_client` fixtures）→ 429 头/body、白名单、
  身份隔离、fail-open 回归；新增 `X-RateLimit-Scope` 断言。

**红-绿垂直切片（一次一个，按此顺序）**：

1. `check` async 化 + `InProcessBucketStore`（同语义）→ 现有 7 例单测改 async 后全绿（**先红**：改签名即红）。
2. fake store 决策透传（含 `retry_after`/`remaining`/`capacity` 不变）。
3. Redis 异常 → 降级到进程内桶 + `rate_limit_degraded` 计数 + 冷却窗口内**不再调用 store**（断言 fake 调用次数）。
4. 假时钟推过冷却窗口 → 再次尝试 Redis；恢复后回到共享路径（断言 scope 从 instance 回到 shared）。
5. `RedisBucketStore`：Lua 语义（capacity/burst/refill/TTL）+ 两实例共享（缝 B）。
6. `http/ratelimit.py` 接入 + `X-RateLimit-Scope` 头 + 429 语义回归（缝 C）。
7. 共享配额压测：`load_test.py --tag p7-shared` 与 §2.7 同参数对比（含 Redis 往返对 p50 的影响）。

**可复跑命令（验收包按此贴原始输出）**：

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'

bash scripts/verify.sh --list          # 先看清单（注意入口是 --layer，不是位置参数）
bash scripts/verify.sh --layer all     # 12 条命令（unit + contract + scripts）
cd apps/api && uv run pytest tests/ai_resilience/test_ratelimit.py -q --junitxml=/tmp/p7.xml

# 部署面（冷卷！否则热卷会"假绿"）
cd '/root/better resume' && docker compose --profile smoke down -v
bash scripts/compose_smoke.sh          # 含新增的"跨副本共享配额"断言
bash scripts/kill_instance_drill.sh    # kill 正在服务的实例 → 状态/报告一致 + 配额不分裂

# 降级语义演练（Redis 分区：不是杀容器，避免 compose DNS 陷阱 P41）
cd apps/api && uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20
```

**口径**：所有数字标清「本机 / CI」「冷卷 / 热卷」；降级演练在**单机 compose** 上做，不等于真实网络分区。

## 8. 影响面与风险

| # | 风险 | 缓解 |
| --- | --- | --- |
| 1 | 每受限请求 +1 次 Redis 往返（延迟） | 只让成本桶共享（Q2 ①）；用 `load_test.py` 同参数实测 p50 差值并写进报告 |
| 2 | Redis 抖动把延迟拖成 `socket_timeout` × 请求数 | 50ms 硬超时 + 30s 冷却窗口（窗口内 0 次尝试）；演练断言 |
| 3 | 跨副本 wall-clock skew 进入配额 | 本机同宿主 = 0；写成显式假设 + 影响上界（2/s 下每 100ms ≈ 0.2 token）；诚实清单 |
| 4 | **配额收紧**（4/s → 2/s、burst 8 → 4）改变真机行为 | Q3 拍板；同步更新 §2.7 与 `test_defaults_are_calibrated_for_real_traffic` 的注释口径 |
| 5 | Redis 键基数（每身份每桶 1 键）无上限 | TTL 兜底；只共享 3 个成本桶；不做每身份键上限 → 诚实清单 |
| 6 | 破坏性签名变更（`check` → async）漏改调用点 | 3 个调用点已 grep 清零（中间件 / main / smoke 脚本）；类型检查 + 全量测试兜底 |
| 7 | 哨兵 failover 窗口内触发一次降级 | 行为正确（降级 → 恢复），演练里断言恢复后 scope 回到 shared |
| 8 | 语义回归（`X-Instance-Id` / 429 / 白名单 / 身份哈希） | 逐条回归测试钉住（缝 C），不靠人工看 |

## 9. 预估

- 代码：1 个新模块（+Lua）+ `ratelimit.py` 重构 + 3 个调用点 + 配置；**1–1.5 天**。
- 测试：3 条缝 + 7 个切片；含真 Redis 集成（本地已起）。
- 演练：冷卷 compose 两轮（`compose_smoke` + `kill_instance_drill`）≈ 10–15 分钟；`fault_probe redis-partition` 1 分钟。
- **真机调用：0 次**（不花钱）。

## 10. 需要你决定的问题（2026-09-30 已全部拍板）

- ~~Q1｜降级语义~~ → **已确认：C**——Redis 不可用时退回进程内桶（配额暂时 ×N = 迁移前的语义），
  配合显式可观测（`ratelimit_degraded` 日志 + `/resilience/stats` 计数 + `X-RateLimit-Scope: instance`）
  与 30s 冷却窗口；**不 fail-closed、不按快照拒绝**。
- ~~Q2｜共享范围~~ → **已确认：只共享 `AI_CALL/ANSWER/HEAVY`**（`shared_buckets` 默认值即此）；`GENERAL/READ` 留在进程内。
- ~~Q3｜配额收紧~~ → **已确认：接受收紧**（单身份 `AI_CALL` 2 副本下 4/s(burst 8) → 2/s(burst 4)），
  并同步改写 `docs/perf/M6-capacity.md` §2.7 的「4× 余量」表述。**不**上调 `ai_call_per_second`。
- ~~Q4｜时间基线~~ → **已确认：① 应用侧注入 wall-clock**（新增 `WallClock.now_ms()` 缝；Lua 只做算术，负 elapsed 钳 0）。
- ~~Q5｜演练与排程~~ → **已确认：加**——`nightly` 增加「限流降级」实验（Redis 分区下断言降级而非 5xx）。

## 11. 诚实清单（本提案自身的未验证项）

- 以上全部是**读代码与文档得到的事实**，本提案**没有跑过任何东西**：3.2 的 Lua 是草图（未在 Redis 上执行过），
  §8 的延迟数字是估计（未实测）。
- 「配额收紧到 2/s 是否影响真机多身份并发」**未实测**（P1-B 的 24 并发是 3 进程 × 8 身份，单身份并发不是瓶颈；
  但那轮用的是 6/s 的旧值）。
- 跨副本 wall-clock skew 的真实分布**未测**（本机 compose 同宿主，测不出 skew）。
- 降级语义的真机表现（Redis 分区时请求是否真的"降级而非变慢"）**未演练**，属 implement 阶段的验收项。
