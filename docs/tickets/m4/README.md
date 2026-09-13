# M4 票据拆分提案（待确认）

> 依据：docs/DECISIONS.md（D05 前端 lib 四件套 / D06 讯飞 AST + edge-tts / D09 砍草稿板 /
> D11 WS 一次性 ticket / D15 一个通道两个消费方 + 一个播放器 / D16 亮点③ 句池归并 / D17 只 mock 系统边界）
> + 分析文档 §4.4（XunfeiAudioService 921 行：AST 协议与三级文本）、§7.4（实时转写时序）、
> §7.5（TTS 播放流）、§12.2（media 接口草图）、§12.3（AstAssembler 移植反射单测）、§12.4（M4 里程碑）。
> 状态：**用户已确认（全选推荐项），执行中；2026-09-14 暂停一次，断点见文末「进度」**。

## 1. M4 验收（§12.4 原文）

> media：转写 WS + TTS 播报 → **语音答题全流程**

## 2. 范围边界

**做**：句池归并算法移植（AstTranscriptionAssembler → Python，含 pgs/rg/重叠度演化/尾缀合并/final）；
讯飞 AST WebSocket adapter（HmacSHA1 URL 签名 / 1280B·40ms 推流 / cn.st 解析 / 心跳）；
**本地可跑的假 adapter**（脚本化转写，供 CI 与演示）；WS 一次性 ticket（D11 落地）+ 转写 WS 端点；
edge-tts 合成 + 缓存 + 失败降级；前端音频采集（AudioWorklet → 16k 单声道 PCM → 40ms 切片）、
WS 客户端（待发队列 / 心跳 / 事件去重）、三级文本消费（面试答案框 + 对话输入框）、单例播放器；
面试房间"语音答题"与题目播报；假 adapter 驱动的端到端证据。

**不做**（D09/D15/D07 硬约束）：草稿板 sketchpad；神态/摄像头；语音唤醒词；实时回声消除（AEC）；
分布式 WS 会话路由（M6）；TTS 长文本三模式（我们只做"点一下读一题"的短文本同步合成，不做 createTask/轮询）。

**纪律**：红-绿 TDD；只 mock 系统边界（讯飞 WS / 浏览器音频 API / 时钟）；内部模块不 mock；
小步提交说 WHAT；**实现中遇到的每个真问题即时记入 PROBLEMS.md**（你两次点名要求）。

## 3. blocking 图

```
T1 句池归并（纯函数，亮点③）─┬─> T2 讯飞 AST adapter ─┐
                              └─> T9 假 adapter 端到端 ─┤
T3 WS ticket + 转写端点 ──────────────────────────────┼─> T8 页面接线 ─┐
T4 TTS(edge-tts) + 端点 ──────────────────────────────┤               ├─> T11 验收
T5 前端采集 + WS 客户端 ──> T6 三级文本消费 ──> T7 播放器 ──────────────┘
T2/T10 真机验证（需凭据）──────────────────────────────────────────────┘
```

| 票 | 标题 | blocking | 预估 |
| --- | --- | --- | --- |
| T1 | 句池归并 AstTranscriptionAssembler（apd/rpl/重叠度演化/final + 三级文本） | M3 | 1.5 会话 |
| T2 | 讯飞 AST adapter（签名/推流/解析/心跳/错误三态） | T1 | 1.5 会话 |
| T3 | WS 一次性 ticket + `/api/v1/media/transcribe` 端点 | T1 | 1 会话 |
| T4 | TTS：EdgeTtsAdapter + 缓存 + `/api/v1/media/tts` | M3 | 1 会话 |
| T5 | 前端采集与 WS 客户端（16k PCM / 40ms 切片 / 待发队列 / 去重） | T3 | 1.5 会话 |
| T6 | 三级文本消费（一个 hook + 共享 store，接两个输入框） | T5 | 1 会话 |
| T7 | 单例播放器（手势解锁 / cacheKey / 超时保护 / revoke） | T4 | 1 会话 |
| T8 | 页面接线：面试房间语音答题 + 题目播报 + 对话页语音输入 | T6 T7 | 1.5 会话 |
| T9 | 假 adapter 驱动的端到端（pytest WS 全流程 + vitest 采集全流程） | T2 T5 | 1 会话 |
| T10 | 真机验证（讯飞凭据 + 真实麦克风 + 真实 edge-tts） | T2 T4 T8 | 0.5 会话 |
| T11 | M4 验收证据 + PROBLEMS 收口 + 简历草稿 + PR | 全部 | 0.5 会话 |

## 4. 既定取舍（对齐 D 决议 + M1–M3 经验）

1. **协议细节不出 adapter**（§4.4 的深模块教训）：WS 层只看到 `TranscriptEvent{kind: replace|archive|final}`，
   句池、pgs、rg、时间戳演化全部关在 `media/assembler.py` 里；上层（WS 端点、前端）不 import 讯飞概念。
2. **一个通道两个消费方**（D15）：前端只有一个 `useTranscription` 与一份 store slice，
   面试答案框与对话输入框都从同一份 `merged/live` 文本取值；不做两套采集。
3. **转写是通道，合成是任务**（§12.2）：TTS 走 HTTP 请求-响应（短文本同步合成 + 磁盘缓存
   `data/tts/{sha256}.mp3`），不做长文本任务/轮询（旧项目那套是给整篇文档用的，我们用不上）。
4. **凭据缺失也要能验收**：讯飞 AST 真机在此环境**无凭据**，所以 T2 的协议实现 + T9 的脚本化 adapter
   双轨并行——**"语音答题全流程"用假 adapter 端到端证明**，真机验证单列 T10 并在验收文档里
   如实标注"未验证（缺凭据）"，绝不用假数据冒充真机结论。
5. **浏览器音频不引入库**：AudioWorklet（不支持时 ScriptProcessor 回退）做 Float32 → 16k 单声道 Int16，
   40ms=1280B 切片与 §4.4 一致；不引 RecordRTC/opus 转码（讯飞要的是 PCM）。
6. **autoplay 策略照旧项目的教训办**：播放器在首次用户手势时用 1s 静音解锁，
   `canplaythrough` 3s 超时保护 + 卸载时 `revokeObjectURL`，避免"点了没声"和 Blob 泄漏。

## 5. 环境事实（影响验收口径）

- 本机**没有讯飞凭据**（appId / accessKeyId / accessKeySecret）→ T10 需要你提供才能做真机；
  在此之前，T2 的代码路径只有单测（假 WS 服务器）覆盖。
- `speech.platform.bing.com:443` 可达 → edge-tts 预期能用真合成；若中途失败，T4 提供降级
  （返回明确错误 + 前端"暂不可用"），并在验收里如实写。
- CI 无法访问麦克风/扬声器 → 前端用假 `MediaStream`/`AudioContext` 单测，真机录音由 T10 人工验证。

## 6. 待确认项

见 `OPEN-QUESTIONS.md`（5 项：讯飞凭据策略、TTS 供应商、前端采集形态、句池移植深度、消费方范围）。


## 进度（暂停断点，2026-09-14）

| 票 | 状态 | 证据 |
| --- | --- | --- |
| T1 句池归并 | ✅ 完成 | tests/media/test_assembler.py 22 例；含 MIN_OVERLAP 修复（PROBLEMS P2） |
| T2 讯飞 AST adapter + 假 adapter | ✅ 完成 | tests/media/test_xunfei_ast.py 10 例（本地假 WS 服务端）；PROBLEMS P3/P4 |
| T3 WS ticket + 转写端点 | ✅ 完成 | tests/test_ws_ticket.py 5 例 + tests/test_media_ws.py 6 例；PROBLEMS P5/P6 |
| T4 TTS(edge-tts) + 缓存 + 端点 | ✅ 完成 | tests/media/test_tts.py 6 例 + tests/test_media_tts_api.py 8 例（401/422/404 路径穿越/503/504/缓存命中） |
| T5 前端采集 + WS 客户端 | ✅ 完成 | src/audio/pcm.ts + capture.ts + transcriptionSocket.ts，21 例单测（重采样/切片/队列上限/去重/重连/释放麦克风） |
| T6 三级文本消费 | ✅ 完成 | src/audio/transcriptStore.ts（replace/archive/final + mergeTranscript 不覆盖手写文本）；面试答案框与对话输入框共用一份 store |
| T7 单例播放器 | ✅ 完成 | src/audio/player.ts（单例/缓存/手势解锁/3s 超时/revoke）+ useTtsPlayback；5 例单测 |
| T8 页面接线 | ✅ 完成 | 面试房间（语音输入/停止/朗读题目）、对话页语音输入、vite ws 代理；src/pages/VoiceWiring.test.tsx 8 例 |
| T9 假 adapter 端到端 | 🔶 后端一半已具备（WS 全流程用例即端到端：ticket→PCM→replace/archive/final）；前端一半未开始 |
| T10 真机验证 | ⏸ 阻塞：等讯飞凭据（BR_XUNFEI_APP_ID / ACCESS_KEY_ID / ACCESS_KEY_SECRET） |
| T11 验收 + PROBLEMS + 简历 + PR | ⬜ 未开始（M4 分支 m4/media 尚未开 PR） |

**续做入口**：`git checkout m4/media` → 先跑 `cd apps/api && uv run pytest -q`（当前应为 465 例全绿，
本地需 `BR_DATABASE_URL=...5433` + `BR_REDIS_URL=...6379`）→ 从 T4 的 HTTP 用例开始，再进 T5。
**注意**：`uv add edge-tts` 已改 pyproject/uv.lock；`Stage.TTS` 与 `MediaSettings` 已加，OpenAPI 尚未重新导出（T4 收尾时记得跑 export_openapi.py + pnpm gen:api）。