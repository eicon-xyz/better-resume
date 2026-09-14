# 压测（docs/perf）

M6-T6 的自研压测脚本：`apps/api/scripts/load_test.py`（asyncio + httpx，不依赖 locust/k6）。
它只做一件事：**对目标服务发固定比例的流量，把延迟分位数、RPS、错误分类如实记下来**。

## 前置条件

- 目标栈已起（M6-T5 的 compose 形态）：nginx 8080 → 2×api（容器内 uvicorn）+ worker + postgres + redis；
  假供应商场景还需要 compose 里的 fake-llm 服务。
- 只需要本机有 `uv`；脚本**不**需要本机 Postgres/Redis，它只发 HTTP。
- 同一时间**只跑一个**压测（不要和 T8 kill 演练、其他压测并行，数字会互相污染）。

## 命令

    cd apps/api
    # 1) 混合场景（read 60% / answer 25% / chat-sse 15%），固定请求数，假上游
    uv run python scripts/load_test.py --scenario mixed --concurrency 20 --requests 2000 \
        --fake-llm --json /tmp/m6-mixed.json

    # 2) 纯 SSE：看首帧延迟与长连接下的并发
    uv run python scripts/load_test.py --scenario chat-sse --concurrency 20 --duration 20 \
        --fake-llm --json /tmp/m6-sse.json

    # 3) 答题：打锁/单飞路径
    uv run python scripts/load_test.py --scenario answer-submit --concurrency 10 --duration 20 \
        --fake-llm --json /tmp/m6-answer.json

    # 4) 真模型（可选，单列，绝不要和假上游数字混在一张表里）：去掉 --fake-llm
    uv run python scripts/load_test.py --scenario chat-sse --concurrency 5 --duration 30 \
        --json /tmp/m6-real.json

参数：`--base-url`（默认 `http://127.0.0.1:8080`）、`--concurrency`、`--requests` 或
`--duration`（互斥，都不给则默认 10s）、`--scenario`、`--model`（作为 `model_ref` 发给服务端；
`--fake-llm` 时默认 `smoke-fake`）、`--fake-llm`、`--timeout`、`--json PATH`。

**耗时**：`--duration N` 的墙钟时间 ≈ N + 场景准备（登录、建会话、生成 3 道题，含一次解析与
出题调用，几秒）。`--requests N` 在高并发下很快跑完，适合冒烟。跑完前脚本不会提前退出。

## 退出码（重要）

| 码 | 含义 |
| --- | --- |
| 0 | **脚本跑完了**。它不代表"没有失败"——失败是数据，看 `failure_kinds` |
| 2 | 配置被拒绝（例如 `--fake-llm` 指向非本机地址、URL 不合法）；此时**一个请求都没发** |
| 3 | 场景没能准备好（登录/建会话/出题失败，或目标不可达） |

## 读数规矩

1. **`--fake-llm` 只允许本机目标**（127.0.0.1/localhost/::1/0.0.0.0）。指向远端会被直接拒绝，
   以免把"真模型的数字"错标成假上游。脚本用 `trust_env=False`，系统代理不会混进链路。
2. **429 不算错误**：限流生效是预期结果，单列 `rate_limited`；`error_rate = 失败数 / count`，
   失败只包括 4xx（非 429）/5xx/超时/传输错误，分类进 `failure_kinds`。
3. **mixed 是固定循环**（12 read / 5 answer / 3 chat 每 20 个请求），不是掷骰子：同样参数的两次
   运行打的是同样比例的端点，数字可比。
4. 报告里必须写清环境（见 `M6-capacity.md` 第 1 节）；**不同机器的数字不可比**。
5. 脚本测的是"目标服务 + 它前面那一层"；模型延迟属于供应商，进程内数字（无 uvicorn/nginx/网络）
   不能当作部署容量。

## JSON 字段

`count / ok / rate_limited / failure_kinds / error_rate / rps / duration_s / p50_ms / p95_ms / p99_ms /
max_ms / sse_first_frame_ms{count,p50_ms,p95_ms,p99_ms,max_ms} / scenario / concurrency / mode /
requested / upstream(fake|real) / fake_llm / model / base_url / target_hosts / timeout_s`

## 测试

`apps/api/tests/test_load_test_script.py`：用 `httpx.MockTransport` 注入传输层（脚本的 seam）跑通
逻辑，**不测性能**，也不需要服务器：

    cd apps/api && uv run pytest tests/test_load_test_script.py -q
