# media

## 职责

实时转写与 TTS 播报（edge-tts + 缓存）。四个转写 adapter，由 `BR_MEDIA__TRANSCRIPTION_ADAPTER` 选择：
**`paraformer-rt`（百炼实时，边说边出字，2026-09 起为本机默认）** / `qwen-asr`（百炼批量，松手出整段）/
`xunfei`（AST 流式 + 句池归并）/ `scripted`（CI 与本地默认）。

## 对外接口

`TranscriptionChannel(start/feed/stop/wait)`、`TtsSynthesizer`、`AstTranscriptionAssembler`、
`EdgeTtsSynthesizer`、`TtsCache`、`ChannelRegistry`、`WS /api/v1/media/transcribe`、`/media/tts`。

## 不变量

1. 协议细节不出 adapter：上层只看到 `TranscriptEvent(replace|archive|final)`。
2. 句池归并是纯函数（apd/rpl/时间重叠+演化/尾缀合并），**单字重叠不合并**（MIN_OVERLAP=2，M4 P2）。
   **边界（P1-C 真机实测）**：`evolves()` 只认演化型包；百炼实时的句中改写（`第二句。街`→`第二句街口响`）
   会每片新建段（26 段 vs 真实 3 句）——所以 **`paraformer-rt` 直连 replace/archive，绝不走句池**；句池只服务讯飞包型。
3. 一个通道两个消费方、一个播放器（D15）；转写**不覆盖**用户手写内容。
4. 音频 GET 需要登录；digest 非 hex 一律 404（防路径穿越）。
5. 供应商失败 → 明确错误（503/504），绝不用假音频糊过去。

## 已知陷阱

- 收尾顺序：停止录制 → 先 stop 通道（产出 final）→ flush → 再关闭 WS；反过来收尾事件发不出去（M4 P6）。
- Vite 开发代理必须开 `ws: true`，否则浏览器连不上转写（M4 P9）。
- 播放器在 jsdom 下会静默不合成（没有 `URL.createObjectURL`/媒体实现），页面级测试要点到播放器才看得见（M4 P11）。
- worklet 分支只在真浏览器验证过回退路径；**讯飞真机仍未验证**（缺凭据，M4 P0）；百炼实时已真机验证（P1-A）。
- 实时通道收尾：`close_timeout` 必须显式（默认 10s，供应商不回关闭帧 → 松手后干等 10 秒，P24）。

## 测试地图

`tests/media/`（**62 例**：句池 / 四个 adapter / TTS）+ `tests/test_media_ws.py` / `test_media_tts_api.py`；
前端 `src/audio/*.test.ts`、`src/pages/VoiceWiring.test.tsx`。

## 常见变更配方

换 ASR/TTS 供应商：实现同一个 Protocol → 假服务端契约测试 → 前端零改动。

真机验证入口（各 1 次真调用，详见 `docs/tickets/p1-post-v/`）：`scripts/media_smoke.py --paraformer-rt-real|--qwen-asr-real --wav PATH`、
`scripts/v3_ws_probe.py --realtime`（穿 nginx 端到端）、`scripts/assembler_real_probe.py`（真机增量包回放句池）。
