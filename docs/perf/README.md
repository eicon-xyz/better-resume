# 压测（docs/perf）

M6-T6 的可复跑压测：**同一个脚本**既能对本机进程内 app 打（默认，数字干净），也能对真服务打。

## 复跑方式

    cd apps/api
    # 1) 进程内 ASGI：测的是应用自身吞吐（不含 uvicorn/nginx/网络）
    uv run python scripts/load_test.py --scenario mixed      --concurrency 20 --duration 15 --fake-llm --rate-limit-off --json /tmp/m6-mixed.json
    uv run python scripts/load_test.py --scenario chat-sse   --concurrency 20 --duration 15 --fake-llm --rate-limit-off --json /tmp/m6-sse.json
    # 2) 限流打开（默认）：看 429 行为，而不是吞吐
    uv run python scripts/load_test.py --scenario mixed      --concurrency 20 --duration 8  --fake-llm --json /tmp/m6-rl.json
    # 3) 打真服务（compose 的 nginx 入口）
    uv run python scripts/load_test.py --base-url http://127.0.0.1:8080 --concurrency 10 --duration 20

前置：本机 Postgres（5433）与 Redis（6379）可用（脚本读仓库根 .env）；`--fake-llm` 时不触网。
每次运行前脚本会把 `llm_scene_bindings` 重置为默认绑定（场景绑定是全局状态，残留会污染测量）。

## 读数字的规矩

1. **进程内模式不含 uvicorn / nginx / 网络**，它回答的是"应用代码的吞吐上限"；要回答"部署形态下多少"必须用 `--base-url`。
2. **不要跨机器比较**：报告里所有数字都绑定环境（见 `M6-capacity.md` 的环境段）。
3. **429 不算错误**：限流拒绝是预期结果，脚本把它们单独计数（`rate_limited`），`error_rate` 只见 5xx/超时。
4. **假 LLM 不是真 LLM**：`--llm-delay-ms` 可以模拟模型延迟，但真实模型的方差远大于此；真模型数字单列。
