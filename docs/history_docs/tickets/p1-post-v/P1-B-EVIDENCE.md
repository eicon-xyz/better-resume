# P1-B 验收包：真模型高并发压测 + 限流桶标定

- 票据：`docs/tickets/p1-post-v/README.md` §2 P1-B；分支 `p1/realtime-asr`
- 时间：2026-09-15；栈：compose `nginx + 2×api + worker + postgres + redis`（场景绑定 `deepseek-flash`，真调用）
- 结论：**完成，待用户验收**。真模型并发从 V2 的 c≤4 推到 **24 并发流**（0 供应商 429/5xx）；
  据实测标定 `ai_call 6→2`、`answer 8→2`（红-绿测试钉住）；标定后天花板实证分毫不差。
- **花费**：真调用 174 次（P1-A ~10 + 本阶段 164），在 Q3 封顶 200 内，已停。

## 1. 压测矩阵与原始读数（完整数字见 `docs/perf/M6-capacity.md` §2.7）

| 阶段 | 设计 | 结果 |
| --- | --- | --- |
| 阶段 1 单身份 | chat-sse c=8/16/32，各 `--requests 40` | 40/40、40/40、32 ok+**8 rate_limited**；首帧 p50 1593→1877ms；0 失败 0 5xx |
| 阶段 2 多身份 | 3 进程并行 × c=8 × requests 16（聚合 24 并发真流） | **48/48 全 ok**，0 供应商 429/5xx，首帧 p50 1555–1970ms |
| 标定后实证 | chat-sse c=16 ×16 | **8 ok + 8 rate_limited**（= 2 副本 × burst 4，与模型一致），0 失败 |

## 2. 标定（红-绿）

- 红：`test_defaults_are_calibrated_for_real_traffic` 断言新值 → `assert 6.0 == 2.0` 失败；
- 绿：`settings/config.py` `ai_call 6.0→2.0`、`answer 8.0→2.0`（理由注释在源码 + §2.7 表）；全量 **693 passed / 0 failed**；
- 实证：重建栈后 c=16 复测，拒绝数与标定模型一致。
- 未改：general 20 / read 15 / heavy 2 / burst 2.0（无供应商成本压力信号，heavy 本就紧）。

## 3. 本轮新事实（进报告 §2.7）

1. **进程内限流 × N 副本 = 单身份配额 ×N**（M3 诚实边界的首次真机量化）：8 个 429 按 5/3 分摊两副本。
   若要跨副本精确配额，需要 Redis 分布式桶——M3 已声明推迟，本轮不新增。
2. **重试放大上限 ×3 且从未触发**：vendor 429/5xx 仅在连接阶段可重试（`max_attempts=3`，退避 0.5/1s），首帧后不重试；
   166 次真调用 0 次重试。
3. **供应商容量**：DeepSeek 在 24 并发流下无 429/5xx，首帧劣化 ~30%——供应商不是这个规模下的约束。

## 4. 未验证项（诚实清单）

1. **供应商 429 真机表现**：166 次调用未触发一次——供应商 429 时的退避/重试/用户观感仍是纸面推演。
2. **>24 并发**：按花费封顶停在 24；更高并发（64+）的供应商行为未测。
3. **单副本部署**的配额（本轮全是 2 副本；单副本=标定值本身，无 ×N 放大）。
4. **跨机 RTT / 真实网络**：延续 V2 未验证项。
5. answer-submit 场景的"限流下表现"口径失真（V2 §2.3）延续：本轮未加思考时间重测答题吞吐。

## 5. 复跑（最短路径；真调用，注意花费）

```bash
cd '/root/better resume/apps/api' && export PATH="$HOME/.local/bin:$PATH"
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy
uv run python scripts/load_test.py --base-url http://127.0.0.1:8080 --scenario chat-sse --concurrency 16 --requests 16 --tag p1b-repro --json /tmp/p1b-repro.json
# 期望：~8 ok + ~8 rate_limited（标定后天花板）；JSON 读 rate_limited 字段（429 不算 failure）
uv run pytest -q --junitxml=/tmp/x.xml   # 693
```
