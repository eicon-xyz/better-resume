# M3 验收证据（ai-resilience：单飞 + 熔断 + 限流接入四链路）

> 日期：2026-09-13 ｜ 分支：`m3/ai-resilience` ｜ 票据：docs/tickets/m3/（T1–T10 全部完成）
> 验收口径（§12.4 原文）：**并发同 key 单次调用有测试证明**。

## 1. 结论

| 项 | 结果 |
| --- | --- |
| §12.4 验收 | ✅ 后端并发用例 + 真模型冒烟双重证据（§2、§3） |
| 后端测试 | **415 passed**（M2 324 → +91），其中 `tests/ai_resilience/` 78 例 **0.08s** 跑完（假时钟） |
| 前端测试 | **115 passed**（M2 104 → +11），eslint 0 warning、`tsc --noEmit` 干净、`vite build` 通过 |
| 本地 CI 矩阵 | **12/12 全绿**（与 workflow 同命令逐条 exit=0，§4） |
| 迁移 | 无 schema 变更（`alembic check` 干净）；新增端点 `GET /api/v1/resilience/stats` 已进契约 |
| 问题记录 | `docs/tickets/m3/PROBLEMS.md`：P0–P10 十条（含 4 条 M2 遗留缺陷） |

## 2. 并发同 key 单次调用（自动化证据）

| 链路 | 用例 | 断言 |
| --- | --- | --- |
| 聊天流（服务级 + 真库） | `test_resilience_concurrency.py::test_concurrent_identical_chat_streams_share_one_vendor_call` | 两路并发同 content → 上游 `stream()` **1 次**、两路文本都是 `你好`、`singleflight_follower=1` |
| 聊天流（单飞层） | `test_stream_fanout.py::test_three_consumers_share_one_upstream` | 3 消费者 → 上游订阅 1 次、帧序列逐帧一致 |
| 迟到订阅 | `test_late_subscriber_replays_from_the_first_frame` | 第 3 帧后加入者仍拿到完整序列 `f0,f1,f2` |
| 值链路（评分） | `test_resilient.py::test_followers_of_an_inflight_call_are_never_rejected` | 熔断器中途打开，在飞 follower 仍拿到结果 |
| 评分链路（真库） | `test_schema_failure_is_replayed_instead_of_recalling_the_vendor` | 同一答案二次提交命中负缓存 → 上游仍 **1 次** |
| 反例（M1 直通） | `test_singleflight.py::test_the_m1_passthrough_would_call_twice` | `DirectAiResilience` 下同场景上游 **2 次**（证明测试有鉴别力） |

## 3. 真模型冒烟（`uv run python scripts/resilience_smoke.py`）

真实 DeepSeek（deepseek-flash），一次运行输出：

```
======== 1. concurrent identical chat streams ========
consumers            : 3
upstream subscriptions: 1
identical payloads    : True -> '你好'
metrics               : {'singleflight_leader': 1, 'singleflight_follower': 2, ..., 'peak_in_flight': 1}

======== 2. real vendor call (DeepSeek) ========
model                 : deepseek-flash
upstream stream calls : 1        # 两个并发同 key 消费者
consumers             : 2
answer                : '用户问的是"用一句话说明什么是熔断器"。这是一个技术概念问题。熔断器有两个常见含义：...'

======== 3. breaker: open -> shed -> half-open -> closed ========
call 0/1/2: AiTimeout（注入的 vendor timeout，3 次失败达到 min_calls）
shedded            : unavailable at stage=evaluation: circuit open (open), retry in 30.0s
vendor calls delta : 0 (expected 0)      # 熔断开态后上游零调用
after half-open    : closed              # 假时钟推进 31s → 半开探测成功 → 闭态

======== 4. rate limiting (token buckets on a manual clock) ========
request 0: allowed=True retry_after=0.00
request 1: allowed=True retry_after=0.00
request 2: allowed=False retry_after=0.50
after 0.5s: allowed=True
```

HTTP 侧的分类映射同源验证（`tests/test_resilience_concurrency.py`）：
上游 vendor timeout → **504 + kind=timeout**；熔断开态 → **503 + kind=unavailable + Retry-After: 5**，
且两次请求之间上游调用数不增长。

## 4. 本地 CI 矩阵（12/12）

```
PASS 01 uv sync --frozen            PASS 07 openapi --check
PASS 02 ruff check                  PASS 08 pnpm install --frozen-lockfile
PASS 03 ruff format --check         PASS 09 web lint
PASS 04 pytest                      PASS 10 web typecheck
PASS 05 alembic upgrade head        PASS 11 web test
PASS 06 alembic check               PASS 12 web check:api
```

执行环境：本机 Docker 不可用 → 原生 **PostgreSQL 14（5433）** + 原生 **Redis 6（6379）**；
CI 仍是 service containers（5432/6379），命令完全一致。本地 `.env`（gitignored）已指向 5433。

## 5. 与提案的偏差（如实记录）

1. **流式单飞是提案外的设计增量**：提案只说"在飞合并 + 广播"，实现中确认了三个必须写清的语义
   ——迟到订阅从头回放、全部消费者离开才取消上游、**完成后不回放**（Q1/Q2 已确认）。
2. **重试不在本模块**：装饰链是 单飞 → 熔断 → 舱壁 → 超时 → 上游，**没有 Retry**；
   传输/schema 重试仍由 llm-gateway 独占（避免重试放大）。原项目 guard 链里有 Retry，我们显式不做。
3. **限流在 HTTP 中间件**，不在 `run()` 内：所以 `run(stage, key, fn)` 签名与 §12.2 逐字一致，
   四个调用点没有为限流改动一行；身份 = 会话 cookie 的 sha256（不查 Redis、不落原文），无 cookie 退化为 IP。
4. **舱壁拒绝不计入熔断失败**，且熔断开态不占舱壁名额（装饰顺序的可观测效果，有专门用例）。
5. **流的熔断记账在流结束时**：打开成功 ≠ 流成功；生产者（广播）是唯一驱动包装器的人，
   因此每场流只记一次成功/失败。
6. **M2 契约变更**：上游 vendor timeout 由 **502 改为 504 + kind=timeout**，
   熔断/舱壁为 **503 + kind=unavailable + Retry-After: 5**；三条 M2 测试随之更新，前端文案同步。
7. **chat 不做完成回放**（`chat_replay_seconds=0`），评分/追问/报告 60s、出题 300s；
   失败只负缓存"不可重试"的 schema 类错误 10s —— M2「评分失败可回滚重答」不变量保持（有回归用例）。
8. **参数全部走 settings**（`BR_RESILIENCE__*` / `BR_RATE_LIMIT__*`），无热更新（重启生效）。
9. **无 Prometheus**（D17）：进程内计数器 + `GET /api/v1/resilience/stats`（需登录）。
10. **M2 遗留缺陷修复**（P0，回放一开就会串号）：出题 key 补 resume/count/language、
    追问 key 补答案摘要、报告 key 补分数摘要、聊天 key 补 model_ref；另有
    `storage.py` docstring 的 SyntaxWarning 一并修掉（P3）。
11. **未做**（按 D07/§12.4 留后续）：Redis 分布式单飞 / fencing / 心跳接管 / 结果回放（M6）、
    压测脚本（M6）、按供应商分桶的熔断、限流封禁名单。

## 6. 复跑方式

```bash
# 后端（本机原生库）
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
cd apps/api && uv run pytest -q                     # 415 passed
uv run python scripts/resilience_smoke.py           # §3 的真实/注入证据

# 前端
pnpm -C apps/web test --run                          # 115 passed
```
