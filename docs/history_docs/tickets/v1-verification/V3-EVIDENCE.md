# V3 证据：语音识别真机（阿里云百炼 Qwen-Audio-3.0-ASR-Flash，批量）

- 时间：2026-09-14（CST）；栈：compose \`nginx + 2×api + worker + postgres + redis\`
- 模型：\`qwen-audio-3.0-asr-flash\`（MaaS 工作区端点，账号相关，只放 \`.env\`）
- 音频：\`data/audio/v3-sample-16k.wav\`（用户提供，16 kHz 单声道 PCM，**5.5s / 175,872 字节**）
- 配置：\`BR_MEDIA__TRANSCRIPTION_ADAPTER=qwen-asr\`、\`BR_MEDIA__ASR_URL\`、\`BR_MEDIA__ASR_MODEL\`

## 1. 直接调用（adapter → MaaS）

\`\`\`
$ uv run python scripts/media_smoke.py --qwen-asr-real --wav ../../data/audio/v3-sample-16k.wav
  audio: v3-sample-16k.wav 5.5s (175872 bytes of 16 kHz mono pcm)
  event: final    '你好，我是来自示例大学人工智能本科的测试用户。'
  request: 175960 wav bytes, release -> text 1.15s
  final  : '你好，我是来自示例大学人工智能本科的测试用户。'
result: ok          # TTS 一并复跑：25200 字节 mp3，头 \xff\xf3d\xc4
\`\`\`

## 2. 浏览器路径（nginx → 一次性 WS 票据 → 二进制 PCM → stop）

\`\`\`
$ uv run python scripts/v3_ws_probe.py
WS open (101)
sent 175872 bytes of 16k pcm (5.5s) in 100ms slices
  [ 0.77s] final: '你好，我是来自示例大学人工智能本科的测试用户。'
WS closed: ConnectionClosedOK code= 1000
total 0.77s, frames=1, final='你好，我是来自示例大学人工智能本科的测试用户。'
PASS
\`\`\`

这条是**端到端**证据：登录 → \`POST /api/v1/auth/ws-ticket\` → 经 nginx 升级 WS（101）→
按 100 ms 切片推 PCM → 发 \`{"type":"stop"}\` → **松手后 0.77s 收到 final 文本** → socket 干净关闭（1000）。
这正是浏览器要走的路径（\`src/audio/transcriptionSocket.ts\` 的 \`stop\` 协议）。

## 3. 错误面（真机）

| 场景 | 结果 |
| --- | --- |
| 缺 \`BR_MEDIA__ASR_URL\` | 构造即报 \`MediaConfigError: qwen-asr needs BR_MEDIA__ASR_URL (the MaaS workspace endpoint)\` |
| 错 key | 供应商 **401 \`InvalidApiKey\`**，我方抛 \`MediaConfigError: qwen-asr returned 401: {...}\` 并记 \`qwen_asr_failed\` 日志；WS 侧会以 \`4411 CLOSE_CHANNEL_FAILED\` 关闭（端点已改为读取 \`channel.failure\`） |
| 空音频（没说话就松手） | 不发请求、不产生事件（测试覆盖） |
| 本机畸形 \`NO_PROXY\`（WSL 导出裸 IPv6） | 记 \`qwen_asr_proxy_env_ignored\` 并退回 \`trust_env=False\`（与 LLM adapter 同一套兜底） |

## 4. 过程中发现并修掉的两个真问题

1. **P20 — \`wait()\` 违反协议，socket 在客户端第一帧就断**：批量 adapter 的 \`wait()\` 必须"阻塞到通道结束"，
   我第一版写成"立即返回" → WS 端点把 \`wait()\` 完成当成"通道结束"，立刻取消任务并关闭连接，
   客户端第一帧就收到 1006（服务端日志只有 \`connection open\`，没有任何报错，非常难查）。
   修法：\`stop()\` 在 \`finally\` 里 set 一个 \`asyncio.Event\`，\`wait()\` 等它；回归测试
   \`test_wait_blocks_until_stop_finished\` 断言"stop 之前 wait 不返回"。
   同一个 adapter 还踩了 **httpx 解析畸形 NO_PROXY 直接抛 \`InvalidURL\`** 的坑（M3 老问题的新位置）→
   补 \`build_client()\` 兜底 + 测试。
2. **P21 — 成功后 socket 以 1006 关闭**：端点返回时没有发 close 帧，客户端把"文本已收到"仍当异常关闭
   （浏览器可能据此弹错误/重连）。修法：成功路径显式 \`websocket.close(code=1000)\`；修复后客户端
   收到 \`ConnectionClosedOK code=1000\`。

## 5. 已声明的产品取舍（与票据 §2 一致）

- **批量**：说话过程中**没有**增量文本；松手后 ~1s 出现整段文本（真机实测 0.77–1.15s）。
- **M4 的句池归并（亮点③）不会被这个 adapter 触发**——它是为增量厂商（讯飞 AST/Paraformer 实时）写的；
  代码与测试仍在，只是本 adapter 的路径不经过它。
- 想"边说边出字"：在百炼开通实时语音识别，再按 B 方案补一个流式 adapter（票据已写明，另开票）。

## 6. 未验证

- 30–60s 长音频（本机只有 5.5s 素材）：多句返回、耗时线性度、请求体大小上限；
- 并发多路转写（registry 限制每用户 1 路，未压并发）；
- 供应商限流/配额错误（本轮未触发 429）；
- **真实浏览器**（V5：权限、边说边打、TTS 播放）——现在栈里已经接的是这个 adapter，随时可测。
