# media

## 职责

实时转写（讯飞 AST / 脚本化 adapter）与 TTS 播报（edge-tts + 缓存）。

## 对外接口

`TranscriptionChannel(start/feed/stop/wait)`、`TtsSynthesizer`、`AstTranscriptionAssembler`、
`EdgeTtsSynthesizer`、`TtsCache`、`ChannelRegistry`、`WS /api/v1/media/transcribe`、`/media/tts`。

## 不变量

1. 协议细节不出 adapter：上层只看到 `TranscriptEvent(replace|archive|final)`。
2. 句池归并是纯函数（apd/rpl/时间重叠+演化/尾缀合并），**单字重叠不合并**（MIN_OVERLAP=2，M4 P2）。
3. 一个通道两个消费方、一个播放器（D15）；转写**不覆盖**用户手写内容。
4. 音频 GET 需要登录；digest 非 hex 一律 404（防路径穿越）。
5. 供应商失败 → 明确错误（503/504），绝不用假音频糊过去。

## 已知陷阱

- 收尾顺序：停止录制 → 先 stop 通道（产出 final）→ flush → 再关闭 WS；反过来收尾事件发不出去（M4 P6）。
- Vite 开发代理必须开 `ws: true`，否则浏览器连不上转写（M4 P9）。
- 播放器在 jsdom 下会静默不合成（没有 `URL.createObjectURL`/媒体实现），页面级测试要点到播放器才看得见（M4 P11）。
- worklet 分支只在真浏览器验证过回退路径；讯飞真机仍未验证（缺凭据，M4 P0）。

## 测试地图

`tests/media/`（句池 22、adapter 10、TTS）+ `tests/test_media_ws.py` / `test_media_tts_api.py`；
前端 `src/audio/*.test.ts`、`src/pages/VoiceWiring.test.tsx`。

## 常见变更配方

换 ASR/TTS 供应商：实现同一个 Protocol → 假服务端契约测试 → 前端零改动。
