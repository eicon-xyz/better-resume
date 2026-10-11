# M6-T6 — 压测脚本与容量报告

- blocking：M6-T5
- 纪律：**只写脚本实测的数字**，注明环境；不做"感觉很快"的结论

## 目标

给项目一套可复跑的压测脚本与一份容量报告：单实例吞吐、SSE 并发、限流/熔断在压力下的行为、
单飞命中率与热层命中率。数字用于说明"瓶颈在哪"，不用于吹性能。

## 交付物

- `scripts/load_test.py`（自研，httpx + asyncio）：
  - 场景：`chat-sse`（并发 SSE 流）、`answer-submit`（并发答题，含单飞/锁路径）、`mixed`（按比例混合）
  - 参数：并发数、持续时间/请求数、目标 base_url、是否注入假 gateway（`--fake-llm` 用本地假服务端，
    避免真模型限流干扰测量）
  - 指标：p50/p95/p99、RPS、错误率、429 数、SSE 首帧延迟、失败分类分布
  - 输出：控制台表格 + `--json` 落盘（验收文档引用）
- `docs/perf/M6-capacity.md`：环境说明（WSL2/容器/native 库）、三组场景的数字、瓶颈分析、
  **不确定项**（真模型延迟波动、单机 Redis、非生产网络）
- `docs/perf/README.md`：怎么复跑（含前置条件与耗时）
- 测试：`tests/test_load_test_script.py`（≥4 例，用小规模参数跑通脚本本体，不测性能）

## 测试

| 用例 | 断言 |
| --- | --- |
| 脚本可跑 | 2 并发 × 5 请求的混合场景退出码 0，输出 JSON 含全部指标字段 |
| 429 计数 | 打开限流并压 `read` 桶 → 429 计数 > 0 且脚本仍正常结束 |
| 假 LLM | `--fake-llm` 时不上外网（断言无出网调用 + 日志标记） |
| 报告字段 | JSON 的 p95 ≥ p50、错误率 = 失败数/总数 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python scripts/load_test.py --scenario mixed --concurrency 20 --duration 20 --fake-llm --json /tmp/m6.json` | 生成报告；数字进 `docs/perf/M6-capacity.md` |
| 真实模型（可选） | 单独跑一次 chat-sse（小并发），标注"含真模型"并与假 LLM 数字分开列 |

## 不做

- 不做分布式压测（单机脚本 + 本机目标）；不做长期稳定性测试（>10 分钟）；
  不引 locust/k6（自研脚本能复用我们自己的 SSE 客户端与错误分类）。

