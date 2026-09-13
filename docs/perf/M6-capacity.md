# M6 容量报告

> 数字来源：**2026-09-14 00:30 CST** 的一次真实起栈（`docker compose`，2×api + worker + postgres +
> redis + nginx + fake-llm），由 `apps/api/scripts/load_test.py` 跑出，JSON 落在 `/tmp/m6-*.json`。
> **没有真模型数字**（见 §2.4）：真机凭据与高并发真模型仍属未验证项。

## 1. 环境（实测时的事实）

| 项目 | 值 |
| --- | --- |
| 宿主 / 内核 | WSL2，`Linux 6.6.114.1-microsoft-standard-WSL2`，Ubuntu 22.04.5 LTS |
| 容器运行时 | Docker Desktop（WSL2 后端）**29.6.2** / compose **5.3.1** |
| 硬件配额 | 20 vCPU / 7 GiB 内存（宿主上还有别的容器在跑：searxng、mysql、rabbitmq…） |
| 拓扑 | **2× api（容器内 uvicorn）+ 1× worker + postgres:16-alpine + redis:7-alpine + nginx:1.27.5** |
| 入口 | nginx（`http://127.0.0.1:8080`）→ 变量 upstream + Docker DNS 轮询两个 api |
| 上游 | **fake-llm 容器**（`--fake-llm --model smoke-fake`）：非流式立即返回、SSE 首帧固定延迟 2s，之后每 0.2s 一片 |
| Redis | **单机单实例**（锁、热层、任务流、单飞都在它上面） |
| Postgres | 同一 compose 内的单实例 |
| 压测机 | 与栈**同机**（loopback），脚本进程与 7 个容器抢同一份 CPU |
| 脚本 | `apps/api/scripts/load_test.py`（`trust_env=False`，系统代理不参与） |
| 栈状态 | 热栈（postgres/redis 已运行 19 分钟，api/worker 由本轮 `up` 新建） |

每组场景之间没有并行压测/演练/测试；场景准备（登录、建会话、生成 3 道题）**不计入**统计窗口。

## 2. 结果

### 2.1 mixed（固定配比：每 20 个请求 12 read / 5 answer / 3 chat-sse）

`--scenario mixed --concurrency 20 --duration 20 --fake-llm --json /tmp/m6-mixed.json`

| 指标 | 值 |
| --- | --- |
| count / ok / rps | 935 / 684 / **41.7** |
| p50 / p95 / p99 / max (ms) | **17.33** / **2464.44** / **3855.69** / 5077.06 |
| error_rate / rate_limited | 0.2492 / **18**（429） |
| failure_kinds | `{"http_409": 233}` |
| sse_first_frame_ms p50 / p95 | 2025.5 / 2447.02 |
| duration_s | 22.41 |

读法：p50 17ms 说明**非流式**链路（读接口 + 限流快路径）非常快；p95/p99 被 chat-sse 拖到 2.4s/3.9s，
因为假供应商首帧固定延迟 2s、且 20 并发下有排队。`http_409` 是并发答题打到"同一题已被回答/不是当前题"
的状态机拒答（脚本固定循环里 answer 占 25%，没有思考时间），不是 500。

### 2.2 chat-sse（纯 SSE 流，20 并发）

`--scenario chat-sse --concurrency 20 --duration 20 --fake-llm --json /tmp/m6-chat-sse.json`

| 指标 | 值 |
| --- | --- |
| count / ok / rps | 174 / 174 / **7.8** |
| p50 / p95 / p99 / max (ms) | **2443.7** / **2721.09** / **2847.42** / 2850.6 |
| sse_first_frame_ms p50 / p95 | **2030.55** / 2253.03 |
| error_rate / failure_kinds | 0.0 / `{}` |
| duration_s | 22.42 |

读法：一次 chat 流 = 首帧 2s + 3 片 × 0.2s ≈ 2.5s，20 并发 → 7.8 rps 是**上游流时长**决定的，
不是我们的瓶颈。首帧 2030ms 里 2000ms 是假供应商的固定延迟：**API+nginx 的增量约 30ms**。
SSE 全程零错误、零 429，说明 `proxy_buffering off` 这条链在 20 并发下没有背压问题。

### 2.3 answer-submit（锁 / 单飞 / 状态机路径）

`--scenario answer-submit --concurrency 10 --duration 20 --fake-llm --json /tmp/m6-answer-submit.json`

| 指标 | 值 |
| --- | --- |
| count / ok / rps | 11701 / 1 / 584.3 |
| p50 / p95 / p99 / max (ms) | 10.72 / 46.83 / 92.77 / 1115.11 |
| error_rate / rate_limited | 0.0299 / **11350** |
| failure_kinds | `{"http_409": 350}` |

`--concurrency 3` 复跑（`/tmp/m6-answer3.json`）：count 7823 / ok 1 / rate_limited **7553** / rps 521.4 /
p50 4.04ms / p95 10.99ms / `http_409: 269`。

读法（**这组数字最容易被误读，必须写清**）：答题脚本**没有思考时间**，同一会话连续打同一接口，
默认限流是 `BR_RATE_LIMIT__GENERAL_PER_SECOND=20`，所以：

- 实测的"吞吐上限"是**限流器**（429 占 96%+），p50 4–10ms 是 429 快路径，不是答题耗时；
- 真正完成的答题只有 1 次（会话里可答的题有限，其余被 409 状态机拒掉）；
- 因此这组数字**不能**当作答题接口的容量，只能说：**默认限流配置下，密集答题会在 API 边界被削峰**。
  要测答题管线的真实吞吐，需要（a）放开/调大限流桶，或（b）给脚本加思考时间、多会话轮转——本轮没做，列入不确定项。

### 2.4 真模型（**未跑**）

尝试过一次小并发真模型运行，但 compose 里的场景绑定当时被 T8 演练改成了 `smoke-fake`，
脚本没有会话 cookie 无法改回（`PUT /api/v1/scenes/*` 全部 401），所以那次运行的 `upstream: real`
**只是标签，实际仍然打在假供应商上**，不能当真实数字。之后已把五个场景恢复为
`openai_compat:deepseek-flash`。

| 指标 | 值 |
| --- | --- |
| 上游 / 模型 | **未验证**：本机未用真模型压测（真机凭据 + 真模型高并发仍是 M6 的未验证项，见 ACCEPTANCE §6） |

## 3. 瓶颈分析（只写这一轮看得到的）

1. **限流器是答题密集路径的第一道瓶颈**：默认 20 req/s 的通用桶把 96%+ 的密集答题请求挡在 429，
   响应时间退化为 4–10ms 的拒绝路径——这是**设计意图**（M3 的削峰），不是缺陷；但也意味着
   "答题吞吐"这个指标在默认配置下测不出来。
2. **SSE 的 p95/p99 由上游流时长主导**：假上游 2s 首帧 + 0.6s 分片；我们自己的增量约 30ms（首帧差）。
   真实供应商（秒级、方差大）会让 p95/p99 更差，但**不能**据此推断我们的代码变慢。
3. **非流式读路径很快**（p50 17ms、429 快路径 p50 4ms），说明 nginx→uvicorn→（Redis 会话/Postgres）
   这一跳在 20 并发内没有明显排队；再往上压才会看到 Postgres 连接池/事件循环的拐点，本轮没压到。
4. **2 个 api 副本确实在分担**：compose smoke 的 12 次 `/healthz` 命中两个不同实例（5/5 或 6/6 分布），
   本报告的三组压测都经由 nginx 轮询。

## 4. 不确定项（引用这些数字前必读）

1. **真模型延迟**：§2.1–2.3 用假供应商；真实供应商 p50 在秒级且方差极大，§2.4 为空。
2. **单机 Redis**：锁/热层/单飞/任务流共用一个 Redis 实例，测不出主从/集群/网络分区行为。
3. **非生产网络**：脚本与栈同机走 loopback，没有真实 RTT、没有跨机带宽限制、没有 LB 抖动；
   生产数字会**更低**，延迟分布形状也不同。
4. **同机资源争抢**：压测进程与 7 个容器共享 20 vCPU / 7 GiB，宿主上还有别的容器。
5. **零延迟假上游**：§2.1–2.3 只说明**我们自己的代码**在"上游近乎无限快"时的上限。
6. **短时窗口（20s 级）**：说明不了内存/连接泄漏、GC 长尾或 Redis 内存增长。
7. **答题场景的限流失真**：见 §2.3 读法——这组数字是"限流下的表现"，不是答题管线容量。
8. **场景准备开销**：每次运行前的登录/建会话/生成 3 道题不计入统计窗口，但它是真实成本。
