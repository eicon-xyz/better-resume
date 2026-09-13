# M3-T6 — 分桶限流中间件（429 + Retry-After）

- blocking：M3-T1
- 纪律：先写失败测试（红），再实现（绿）；时钟注入，测试不真等 1 秒

## 目标

§4.1.4 的限流矩阵（通用 20/s；answer 8/s、heavy 2/s、read 15/s、ai-call 6/s）落到
Starlette 中间件：按"路由类别"分桶，令牌桶按身份计数，超限返回 429 + Retry-After + 统一错误体。

## 交付物

- ai_resilience/ratelimit.py：TokenBucket（容量 = rate × burst，按注入 Clock 补充）+
  RateLimiter（check(bucket, identity) -> Decision{allowed, retry_after}；空桶惰性清理）
- http/ratelimit.py：RateLimitMiddleware
  - 桶路由表（常量）：/api/v1/chat/**/stream、/api/v1/interview/** 的 AI 端点 → ai-call；
    POST .../answers → answer；POST /sessions、.../finish、上传 → heavy；
    GET 读类 → read；其余 → general
  - 身份：sha256(cookie 值)[:16]（不落原文、不查 Redis）；无 cookie 退化到 request.client.host
  - 放行时回写 X-RateLimit-Bucket / X-RateLimit-Remaining（可观测）
  - 超限：429 {"detail": "...", "bucket": ..., "retry_after": n}，头部 Retry-After: n
  - BR_RATE_LIMIT__ENABLED=false 时整体旁路（本地开发/演示用，**默认开启**）
  - 中间件失败绝不 500：内部异常 → 记日志 + 放行（fail-open，限流不是正确性）
- 白名单：/healthz、/docs、/openapi.json、静态资源不限流
- 测试：tests/ai_resilience/test_ratelimit.py + tests/test_ratelimit_http.py（≥12 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 桶内突发 | 容量内全部 200；第 N+1 个 429 |
| 假时钟补桶 | advance 后恢复放行，且 Retry-After 合理（>0 且 ≤ 1/rate） |
| 身份隔离 | A 打满不影响 B（两个 cookie） |
| 无 cookie | 退化到 IP 维度，仍生效 |
| 分桶隔离 | 打满 read 不影响 general 的另一个路由 |
| 白名单 | /healthz 连打 100 次全 200 |
| 头部 | 响应带 X-RateLimit-Bucket/Remaining；429 带 Retry-After |
| 关闭开关 | enabled=false 时连打不 429 |
| fail-open | 检查函数抛异常时请求仍正常通过 |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_ratelimit.py tests/test_ratelimit_http.py | 全绿 |
| 真实 curl（T10） | 连打 /api/v1/chat/sessions > 阈值 → 出现 429 与 Retry-After |

## 不做

- 不做 Redis 全局限流（M6）；不做封禁名单；不引 SlowAPI；不做"按 token 计费的配额"。

