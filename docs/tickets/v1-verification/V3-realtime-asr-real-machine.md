# V3 — 实时语音识别真机（改用阿里云百炼 Paraformer，原讯飞 AST）

- blocking：需要一个 **阿里云百炼（DashScope）API key**（\`sk-...\`）并在百炼控制台**开通实时语音识别**
- 纪律：真机失败就写失败原因（凭据缺失/网络/字段不符），不允许"跳过但不说"；
  证据写明实际用的是哪家，不用别家的结果冒充

## 为什么改用阿里（2026-09-14 决策）

火山方舟账号未充值、模型未开通；讯飞实时语音转写需要另外申请三件套。用户选择阿里云。
百炼的 **Paraformer 实时语音识别** 与 LLM 用**同一个 DashScope key**（少一套凭据），协议是
WebSocket（首帧 JSON \`run-task\` + 二进制音频帧 + \`finish-task\`，服务端回 \`event: result\` 增量结果），
可以映射到我们已有的句池归并（M4 的 \`AstTranscriptionAssembler\`）。

## 目标

1. 用真机验证**实时** ASR：握手鉴权、16k PCM 推流、增量句（\`sentence_end\`）与最终结果、松手后 final 不丢；
2. 复用 M4 的句池归并：真机增量句 → \`TranscriptEvent\` → 归并成句（不得重复整句、不得吃掉尾字）；
3. 错误面：错 key → 明确鉴权错误；模型未开通 → 明确错误码；异常断连 → 有界重连后失败退出。

## 交付物

- **新 adapter**（缝已存在，先出小提案再写）：\`apps/api/src/better_resume/media/adapters/dashscope_paraformer.py\`
  - 实现 \`TranscriptionChannel\` 协议（\`start/send_audio/stop/wait\`），复用 M4 的 \`TranscriptEvent\` 模型
  - 设置：\`BR_MEDIA__TRANSCRIPTION_ADAPTER=dashscope\`、\`BR_MEDIA__DASHSCOPE_WS_URL\`、模型名（默认
    \`paraformer-realtime-v2\`）、\`BR_DASHSCOPE_API_KEY\`
  - 测试：本地假 WebSocket 服务端（M4 对讯飞就是这么测的）覆盖握手/增量/最终/错误码/有界重连
- \`apps/api/scripts/media_smoke.py\` 增加 \`--dashscope-real --wav PATH\`：把 16k 单声道 PCM 按实时速率
  （或标注倍速）推流，打印原始帧片段、归一后的句子序列、final 与耗时
- \`docs/tickets/v1-verification/V3-EVIDENCE.md\`：原始输出（脱敏）+ 字段映射表（DashScope JSON → 我方模型）
  + 错误码实测 + 音频时长/调用次数
- 若凭据/开通拿不到：写"环境不具备（缺 X），未验证"，并保留假服务端 dry-run 证据

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 假服务端 | 握手、增量句、\`sentence_end\`、final、错误码、断连重试全部有测试（不需要真 key） |
| 真机握手 | WebSocket 101；\`task-started\` 事件到达；日志时间戳单调 |
| 真机转写 | 与音频内容人工核对一致（不一致就写差异）；**句池归并不产出重复整句** |
| 尾包 | 松手后 \`finish-task\` → \`task-finished\` 且 final 文本落库（不缺尾字） |
| 错误面 | 错 key → 鉴权错误；未开通 → 明确错误码；两者在 API 层映射为 503/502 并留日志 |
| 成本 | 记录音频时长与调用次数（百炼新账号通常有免费额度，以控制台为准） |

## 现有音频素材

\`data/audio/v3-sample.mp3\`（用户提供，5.5s，48k）已转成 \`data/audio/v3-sample-16k.wav\`
（16 kHz 单声道 PCM，5.5s，gitignored）。**5.5 秒只够验握手+一两句**；要验句池归并/尾包，
需要 30–60 秒录音（用户补一段即可）。

## 不做

- 不做方言/远场/多说话人评测；不做 ASR 质量打分；不删讯飞 adapter（只是本阶段不验它）

## 预估

1–1.5 会话（adapter + 假服务端测试 + 真机验证脚本）；真机调用量：几分钟音频。
