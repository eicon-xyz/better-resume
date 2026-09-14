# V3 — 语音识别真机（阿里云百炼 Qwen-Audio-3.0-ASR-Flash）

- blocking：需要一个 **百炼（DashScope）API key**（已有）+ 账号可调用 **qwen-audio-3.0-asr-flash**
- 纪律：真机失败就写失败原因；**产品行为差异要明说**（见 §2 的取舍），不用"能转写"掩盖"没有实时增量"

## 1. 预检结果（2026-09-14，已实测）

用户给的调用方式（MaaS 工作区端点）：

\`\`\`
POST https://ws-3foqfy9ysbn66ik2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
Authorization: Bearer $DASHSCOPE_API_KEY
Content-Type: application/json
X-DashScope-SSE: disable
{"model": "qwen-audio-3.0-asr-flash",
 "input": {"messages": [{"role": "user", "content": [{"type": "input_audio",
   "input_audio": {"data": "data:audio/wav;base64,<...>"}}]}]},
 "parameters": {"format": "wav", "sample_rate": "16000"}}
\`\`\`

| 实测 | 结果 |
| --- | --- |
| \`data:audio/wav;base64,...\`（用户那段 5.5s 录音） | **200，1.15s** 返回：\`text="你好，我是来自重庆大学人工智能本科的杨明。"\` |
| 同一个请求体里 \`sentence\` | \`{sentence_id:1, begin_time:320, end_time:4760, sentence_end:true, text:..., words:[12 个带时间戳的词]}\` |
| 响应字段 | 顶层 \`{output, request_id, sentence, text, usage}\`；\`output\` 里是 \`{request_id, sentence, text}\` |
| 直接传裸 base64（不带 \`data:\` 前缀） | **500**（必须用 data URI）→ 适配器要用 data URI，**不需要** OSS/公网 URL |
| \`X-DashScope-SSE: enable\` | 200/0.76s，但按行读不到 \`data:\` 帧（本票不依赖它，未深究） |

结论：**同一把百炼 key 就能做语音识别**，不用再申请讯飞三件套，也不用把音频传到公网。

## 2. 产品行为取舍（需要用户拍板）

这个模型是**整段音频 → 一次返回**（批量），不是"边说边出字"的实时流：

| 方案 | 体验 | 代价 |
| --- | --- | --- |
| **A. Qwen-Audio-3.0-ASR-Flash（本票默认）** | 按住说话 → **松手后约 1–2s** 出现整段文本（可带词级时间戳） | 说话过程中没有增量文本；M4 的**句池归并**（亮点③）不会被这个 adapter 触发（它是为增量厂商写的） |
| B. Paraformer 实时（原计划） | 边说边出字，句池归并生效 | 需要在百炼**另外开通**实时语音识别；再写一个流式 adapter（1–1.5 会话） |
| C. A 先做，B 后补 | 先可用，后补实时 | 两个 adapter 共存（现有 \`TranscriptionChannel\` 缝天然支持） |

**建议 A**（今天就能验、零新凭据），并在文档/前端提示里写明"松手后出字"；如果之后想要边说边出字再做 B。

## 3. 交付物（方案 A）

- \`apps/api/src/better_resume/media/adapters/qwen_asr.py\`：实现现有 \`TranscriptionChannel\` 协议
  - \`start()\` 起缓冲；\`send_audio(pcm)\` 追加；\`stop()\` 把缓冲包成 16k 单声道 WAV → data URI →
    POST 上面的端点（\`X-DashScope-SSE: disable\`）→ 产出 **一个 final \`TranscriptEvent\`**
    （文本；词级时间戳可选映射到 segments）→ \`wait()\` 结束
  - 设置：\`BR_MEDIA__TRANSCRIPTION_ADAPTER=qwen-asr\`、\`BR_DASHSCOPE_ASR_URL\`（工作区端点，账号相关，
    只放环境变量）、\`BR_MEDIA__ASR_MODEL\`（默认 \`qwen-audio-3.0-asr-flash\`）、key 复用
    \`BR_DASHSCOPE_API_KEY\`
  - 错误：4xx/5xx → 明确的 mediia 错误 + WS 关闭码；超时用 M4 已有的有界等待
- 测试：本地假 HTTP 服务端（M4 对讯飞就是假 WS 服务端）覆盖：data URI 组装、成功解析、空音频、
  4xx/5xx、超时、超大音频（>请求上限时的行为）
- \`apps/api/scripts/media_smoke.py --qwen-asr-real --wav PATH\`：真机跑一段音频并打印响应摘要与耗时
- \`docs/tickets/v1-verification/V3-EVIDENCE.md\`：真机输出（脱敏）+ 字段映射表（DashScope → 我方模型）
  + 耗时 + 错误面 + 与流式方案的差异说明
- 若用户要 B：另开一票（不塞进本票），保持"一票一个可验收行为"

## 4. 测试与验收

| 用例 | 断言 |
| --- | --- |
| 假服务端 | data URI 前缀正确、WAV 头合法（16000/单声道/16bit）、成功解析、错误码、超时、空音频 |
| 真机 | 同一段音频的文本与人工核对一致；5.5s 音频 ≤3s 返回 |
| 端到端 | WS 转写链路（M4）在 \`qwen-asr\` 下：松手后前端拿到 final 文本；**不覆盖手写输入**；TTS 播报不受影响 |
| 错误面 | 错 key → 401/403 可读；模型不可用 → 明确错误；两者在 API 层有日志与关闭码 |
| 诚实性 | 证据里写明"批量、松手后出字、无增量"，不声称具备实时增量能力 |

## 5. 现有音频素材

\`data/audio/v3-sample.mp3\`（用户提供）→ \`data/audio/v3-sample-16k.wav\`（16k 单声道 PCM，**5.5s**，gitignored）。
预检已用这段音频跑通。**30–60 秒**的录音能额外验证：长音频是否返回多句、耗时线性度、请求体大小上限。

## 6. 不做

- 不做方言/远场/多说话人评测；不做 ASR 质量打分；不改 M4 的句池归并（它服务增量厂商）；
  不删讯飞 adapter（保留，未验证）

## 7. 预估

方案 A：**1 会话**（adapter + 假服务端测试 + 真机脚本 + 证据）；方案 B 追加 1–1.5 会话。
