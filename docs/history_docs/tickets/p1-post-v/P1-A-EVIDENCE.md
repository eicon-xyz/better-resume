# P1-A 验收包：Paraformer 实时 ASR（边说边出字）

- 票据：`docs/tickets/p1-post-v/README.md` §2 P1-A；分支 `p1/realtime-asr`（基于 main = `e202eab`）
- 结论：**完成，待用户验收**。红-绿 TDD；新增 13 个单测；全量后端 **692 passed / 0 failed**、前端 **161 passed**；
  真机证据四组；**松手→final 从 10.1s 修到 1.1s**（过程中发现并修掉 P24）。

## 1. 接入方法（预检实测，2026-09-15）

`wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference` —— 与批量 ASR 同一业务空间域名、
同一把 `BR_DASHSCOPE_API_KEY`（**API 不变、零新凭据**）。握手 `Authorization: Bearer` 鉴权；
交互：run-task → task-started → 16k 单声道 PCM（100ms/帧）→ 增量 result-generated → finish-task → task-finished。
预检（3× 速率灌音频）：0.047s task-started；10 个增量 partial；1.80s final 全句。

## 2. 交付物

- `media/adapters/paraformer_rt.py`：实现 `TranscriptionChannel`（start/feed/stop/wait）。
  增量映射沿用讯飞 M4 先例：partial→`replace`（live 区）、句尾→`archive`（追加已完结句）、收尾→`final`（全文快照）；
  **懒连接**（无音频不建连）；尾部预算 `finish_timeout_seconds=2s`；`close_timeout=1s`；供应商错误 → `AiUnavailable`（WS 关闭码 4411）；不做流中重连（语音不可重放，重连=再按一次）。
- 设置：`BR_MEDIA__TRANSCRIPTION_ADAPTER=paraformer-rt`、`BR_MEDIA__ASR_WS_URL`（留空=从 asr_url 域名推导）、
  `BR_MEDIA__ASR_REALTIME_MODEL`（默认 `paraformer-realtime-v2`）；factory 接线；compose 透传；`.env.example` 补变量名（只列名）。
- 脚本：`media_smoke.py --paraformer-rt-real --wav PATH`；`v3_ws_probe.py --realtime`（**边发边收**，见 P25）。
- 默认切换：仓库根 `.env`（gitignored）已切 `paraformer-rt`，栈已重建生效；代码默认仍 `scripted`（CI/hermetic）。

## 3. 真机证据（原始输出摘录）

| # | 场景 | 关键数字 |
| --- | --- | --- |
| a | 直连冒烟 1×（`media_smoke.py --paraformer-rt-real`） | first partial **0.61s**；replace=9 archive=1 final=1；全句 `你好，我是来自示例大学人工智能本科的测试用户。`；TTS ok |
| b | 容器内直连 1×（无 nginx） | 增量 0.53→4.69s **随说话逐步到达**；archive 5.44s |
| c | **端到端 nginx**（`v3_ws_probe.py --realtime`，修复后） | first_partial **0.56s**；replace 0.56→4.73s；archive 5.54s；**final 6.62s（松手→final ≈1.1s）**；关闭码 **1000**；PASS |
| d | 修复前对照（同一端到端） | final 15.63s（松手→final **10.1s**）→ 根因 P24（websockets `close_timeout` 默认 10s） |

## 4. 测试

- 新增 `tests/media/test_paraformer_rt.py`（13 例）：run-task 契约帧 / 增量映射 / 双句归并 / finish-task 时序 /
  task-failed→AiUnavailable / 无音频不建连 / 连接失败上报 / 尾部预算（卡死干净收尾、final 不丢）/
  空帧忽略 / 配置错误 / WS URL 推导 / factory 接线 / **close_timeout≤1s**（锁住 P24 修复）。
- 全量：后端 **692 passed / 0 failed / 0 skipped**（junitxml 实读）；前端 **161 passed (23 files)**；ruff format/check 干净。
- 契约三件套：本票**无 REST 模型变更**——`export_openapi.py` 复跑后 `git diff` 为空、`extract_api_index.py --check` 通过。

## 5. 未验证项（诚实清单）

1. **真实浏览器手测（等用户）**：按住说话时文本流畅追加、手写不被覆盖、TTS——本阶段验到 WS 协议层（nginx 端到端）；
   浏览器采集代码与批量时代相同（P22 已接 destination），但真实麦克风的抖动节奏未在端到端里跑过。
2. 长音频（>30s 连说）、多句连续输入的延迟/内存线性度。
3. 真机掉线：设计为不重连（4411），单测覆盖连接失败路径，真机掉线未自然触发。
4. 浏览器矩阵（Safari/Firefox/蓝牙）延续 V 阶段未验证。

## 6. 与提案的偏差

- 尾部预算 `finish_timeout_seconds=2s` 与 `close_timeout=1s` 为实现中发现的真实问题（P24），先红-绿后修，提案里未预写。
- `v3_ws_probe.py` 增加 `--realtime` 并改为边发边收（P25）：原"发完才收"会把增量时序塌缩，差点把正确实现误判为坏的。

## 7. 复跑（最短路径）

```bash
cd '/root/better resume' && export PATH="$HOME/.local/bin:$PATH"
cd apps/api && export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q --junitxml=/tmp/x.xml                                     # 692
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/v3-sample-16k.wav
uv run python scripts/v3_ws_probe.py --realtime                            # 需栈在跑（.env 已切 paraformer-rt）
cd '/root/better resume' && pnpm -C apps/web test --run                    # 161
```
