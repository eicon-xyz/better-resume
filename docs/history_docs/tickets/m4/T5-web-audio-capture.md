# M4-T5 — 前端采集与 WS 客户端

- blocking：M4-T3
- 纪律：先写失败测试（红），再实现（绿）；只 mock 浏览器音频 API（系统边界）

## 目标

D05 的 lib 四件套之一 `audioTranscription` 落地：麦克风 → 16k 单声道 PCM → 40ms(1280B) 切片 →
WS 上行；下行事件去重后交给消费方。

## 交付物

- `src/audio/pcm.ts`（纯函数，重点单测）：`resampleTo16k(float32, inputRate)`、
  `encodePcm16(float32)`、`sliceFrames(int16, 640)`（640 样本 = 40ms）
- `src/audio/capture.ts`：`startCapture({onFrame})`——AudioWorklet（回退 ScriptProcessor），
  返回 `stop()`；权限被拒 → 明确错误
- `src/audio/transcriptionSocket.ts`：`createTranscriptionSocket({url, ticket, onEvent, onStatus})`
  - CONNECTING 期间最多缓存 24 帧（照 §7.4），连上后按序 flush
  - 心跳超时 → 重连；重连成功后不重放旧帧（音频有时效性）
  - `shouldApplyEvent`：revision 单调 + key 去重（丢弃过期/重复帧）
- `src/audio/useTranscription.ts`：把 capture + socket + store 串起来的状态机（idle/connecting/live/error）
- 测试：`pcm.test.ts`（≥10 例：重采样边界、半帧补齐、静音）、`transcriptionSocket.test.ts`（假 WS）

## 测试

| 用例 | 断言 |
| --- | --- |
| 重采样 48k → 16k | 输出长度 = 输入/3（±1）；频率 1kHz 正弦仍为 1kHz（过零计数） |
| PCM16 编码 | 0 → 0x0000；±1.0 → ±32767（不溢出） |
| 切片 | 1500 样本 → 2 帧（640+640）+ 余 220 缓冲 |
| 连接前音频 | 前 24 帧入队；连接后按序 flush；第 25 帧起丢弃（计数上报） |
| 过期帧 | revision 回退的事件被丢弃 |
| 重连 | 断开 → 重连 → 状态回 `live`；旧帧不重放 |
| 停止 | stop() 释放麦克风轨道、关闭 WS、无定时器残留（fake timers 断言） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 全绿（115 → 更多） |
| `pnpm -C apps/web lint` / `typecheck` | 0 warning / 0 error |

## 不做

- 不做回声消除/降噪（浏览器默认）；不做 opus 转码；不做录音回放（只做转写）；
  不上传原始音频到服务器（隐私：只上行 PCM 到转写通道，不落盘）。

