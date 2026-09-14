# V 阶段验收包：验证欠账收口（真模型 / 真机 / 故障注入 / 浏览器）

- 阶段：V（M6 之后的验证欠账），分支 `v1/verification`；票据与进度见 `README.md`
- 环境：WSL2 Ubuntu 22.04.5 / Docker Desktop 29.6.2 + compose 5.3.1 / 20 vCPU / 7 GiB
- 结论：**V1–V6 全部完成**；过程中发现并修掉 **7 个真 bug**（P17–P23），全部先红-绿补测试再修。

## 1. 逐票结果与证据

| 票 | 结论 | 关键数字 | 证据 |
| --- | --- | --- | --- |
| **V1** 真模型四链路 + 失败面 | ✅ | 四链路全通；真 `usage.total_tokens=1347`；worker 1.0 s 写出总结；缺凭据 → **503 点名 `BR_REAL_SMOKE_MISSING_KEY`** | `V1-EVIDENCE.md` |
| **V2** 真模型容量 + 拐点 | ✅ | 真机 chat p50 **1922 ms**、首帧 p50 **1197 ms**（我们自己的增量 ~30 ms）；分级加压有效吞吐被限流钉在 **~23 ok/s**，c=80 拒绝路径 p50 **134 ms**，全程 0 个 5xx | `V2-EVIDENCE.md` + `docs/perf/M6-capacity.md` §2.4–2.6 |
| **V3** 语音识别真机（阿里百炼 Qwen-Audio-3.0-ASR-Flash，**批量**） | ✅ | 5.5 s 音频 **1.15 s** 出文本；**WS 端到端（nginx → 票据 → PCM → stop）0.77 s 收到 final，关闭码 1000**；错 key → 401 可读；缺配置 → 点名变量 | `V3-EVIDENCE.md` |
| **V4** 第二家 LLM 平台（百炼 qwen-plus） | ✅ | **零代码**接入（一行 SQL + 一次绑定）；四链路全通、`usage=70`；与 DeepSeek 字段/事件完全同构；PUT 后两个副本 **0.9 s** 内收敛 | `V4-EVIDENCE.md` |
| **V5** 真实浏览器人工手测 | ✅ | 用户本机 Chrome：两次不同句子**追加**显示、手写内容未被覆盖、TTS 正常 | `V5-EVIDENCE.md` |
| **V6** 浸泡 + 故障注入 | ✅ | Redis 冻结 20 s：仅依赖它的接口 2 s 超时、解冻 2.3 s 自愈；重启 → 旧 cookie **503**（会话确实丢）；**worker 崩溃后任务 59.3 s 被接管并完成**；10 分钟浸泡 **600 请求 0 失败**，非会话键 +2、PG 连接 0 增长、Redis 内存 +0.01 MB | `V6-EVIDENCE.md` |

## 2. 发现并修复的 7 个真 bug（P17–P23）

| 编号 | 一句话 | 修法 | 测试 |
| --- | --- | --- | --- |
| P17 | 会话后端不可用返回 500 | `SessionBackendUnavailable` → **503 + Retry-After**（"问不到 Redis" ≠ "你未登录"） | `tests/test_identity_backend_down.py`（4 例） |
| P18 | 场景绑定缓存是每进程且无 TTL → 另一副本继续用旧绑定（曾表现为 8×503） | 缓存带时间戳 + TTL（默认 5 s）+ 注入时钟；线上验证 2.2 s / 0.9 s 收敛 | `tests/llm_gateway/test_scene_binding_propagation.py`（5 例） |
| P19 | 流式 `usage` 没主动请求 → 换平台就静默丢 token 统计 | 按模型行 `extra.stream_usage=true` 发 `stream_options`（默认关，避免不认该字段的厂商 400） | `test_openai_compat.py` 新增用例 |
| P20 | 批量 ASR 的 `wait()` 立即返回 → WS 端点把"wait 完成"当通道结束，客户端第一帧就 1006；同一 adapter 还踩了畸形 `NO_PROXY` | `wait()` 等 `stop()` 完成；`build_client()` 兜底 `trust_env=False` | `tests/media/test_qwen_asr.py` 新增 2 例 |
| P21 | 成功路径不发 close 帧 → 客户端报 1006（即使文本已收到） | 成功路径显式 `websocket.close(code=1000)` | 端到端探针：`1006 → ConnectionClosedOK 1000` |
| P22 | 浏览器采集节点没接到 `destination` → 真实浏览器可能一帧不产生 | 采集节点经**零增益 sink** 接通 destination，`stop()` 断开 | `apps/web/src/audio/capture.test.ts` 新增连通性用例 |
| P23 | 合并规则按增量语义写 → 批量 ASR 第 2 次起文本被丢弃（"第一次有字、后面没字"） | 新整段**追加**、同段去重、仍绝不覆盖手写内容；提示文案同步 | `transcriptStore.test.ts` 新增 2 例 + 用户复测 |

## 3. 自动化回归（本阶段收口时）

| 项 | 结果 |
| --- | --- |
| 后端 | **678 passed / 0 failed**（M6 收口时 648 → +29：真机脚本、故障探针、身份降级、绑定传播、批量 ASR） |
| 前端 | **161 passed**（M5 时 158 → +3：采集连通性、追加语义 ×2） |
| 静态检查 | ruff format/check、eslint、tsc 全部干净 |
| 端到端探针 | `scripts/v3_ws_probe.py`：nginx → 票据 → 推 PCM → 0.7–0.9 s 收到 final → 关闭码 1000 |
| 既有验收 | `scripts/compose_smoke.sh`、`scripts/kill_instance_drill.sh`、`scripts/fault_injection_drill.sh` 均可复跑 |

## 4. 未验证项（诚实清单）

1. **真模型高并发**：V2 只到 c≤4（不打供应商高并发）；真机 429/配额错误未触发。
2. **讯飞真机、星云真机**：改用阿里百炼后未验证（票据里写明"环境不具备/改用他家"）；火山方舟账号未开通模型（404 `ModelNotOpen`，已弃用）。
3. **长音频 ASR**：本机素材 5.5 s；已用循环音频在供应商侧探到 120 s 仍 200，但**端到端**只验到 5.5 s。
4. **浏览器矩阵**：只测了用户本机 Chrome；Safari/Firefox、蓝牙耳机、设备切换未覆盖。
5. **实时增量转写**：批量 ASR 的既定取舍——说话过程中没有增量文本，M4 句池归并不被这条路径触发。
6. **Redis 集群/多可用区/网络分区、>10 分钟浸泡**：仅单机单实例 + 10 分钟。
7. **真实 LB/跨机 RTT**：nginx 在 compose 内网，无生产网络特征。

## 5. 与提案的偏差

| 偏差 | 原因 | 影响 |
| --- | --- | --- |
| V3 从"讯飞 AST / Paraformer 实时"改为"百炼 Qwen-Audio-3.0-ASR-Flash（**批量**）" | 用户决策：方舟未充值、讯飞需另申请；该模型同一把百炼 key 可用 | 产品语义变化（松手后出字、无增量），已在 V3 票据 §2 与 V5 清单写明 |
| V4 从"星云工作流"改为"百炼 OpenAI 兼容（qwen-plus）" | 同上；且零代码即可验"换平台不发版" | 星云真机仍列为未验证 |
| 新增 4 个业务代码修复（P17–P20）与 3 个前端修复（P21–P23） | 都是验证过程暴露的契约错误，非新功能 | 每项都先补红-绿测试；未改变既有 API 契约 |
| 交付物多出 `apps/api/scripts/v3_ws_probe.py`、`fault_probe.py`、`real_model_smoke.py` | 让每张票都可复跑 | 无 |

## 6. 怎么复跑（最短路径）

```bash
cd '/root/better resume' && export PATH="$HOME/.local/bin:$PATH"
cd apps/api && export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q                                   # 678
uv run python -m scripts.real_model_smoke          # V1/V4（真模型四链路；需 .env 里的 key）
uv run python scripts/media_smoke.py --qwen-asr-real --wav ../../data/audio/v3-sample-16k.wav   # V3
uv run python scripts/v3_ws_probe.py               # V3 端到端（需栈在跑）
cd '/root/better resume' && bash scripts/fault_injection_drill.sh --quick    # V6（15 分钟内）
pnpm -C apps/web test --run                        # 161
```
