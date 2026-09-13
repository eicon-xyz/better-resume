# M4-T2 — 讯飞 AST WebSocket adapter

- blocking：M4-T1
- 纪律：先写失败测试（红），再实现（绿）；**用本地假 WS 服务器做契约测试，不 mock 内部模块**

## 目标

按 §4.4 实现 `XunfeiAstAdapter`：URL HmacSHA1 签名 → 建连 → 1280B/40ms 推流 → 解析
`data.cn.st.rt[].ws[].cw[].w` → 交给 T1 的 assembler → 产出归一事件；连接/心跳/错误全部关在 adapter 内。

## 交付物

- `media/adapters/xunfei_ast.py`：
  - `build_signed_url(app_id, access_key_id, secret, *, sample_rate=16000, lang="autodialect")`
    （HmacSHA1 + base64 + urlencode，纯函数，单测锁字节）
  - `XunfeiAstAdapter(TranscriptionChannel)`：`start(ctx)` / `feed(pcm)` / `stop()`
  - 推流节流：内部按 1280B/40ms 从缓冲取帧（用注入时钟，测试零真实等待）
  - 心跳与重连：ping 间隔、最大重连次数、重连期间的帧丢弃/缓存策略（明确写进 docstring）
  - 错误三态复用 M3 的 `AiTimeout/AiOverloaded/AiUnavailable`（不给 media 造第二套分类）
- `media/adapters/scripted.py`：`ScriptedTranscriptionChannel`——按脚本产出 replace/archive/final 事件，
  供 CI 与本地演示（**不是 mock 内部模块**：它实现的正是 `TranscriptionChannel` 这个系统边界）
- 测试：`tests/media/test_xunfei_ast.py`（≥12 例）+ 一个本地 `websockets` 假服务端做端到端契约

## 测试

| 用例 | 断言 |
| --- | --- |
| 签名函数 | 固定输入 → 固定 query 串（含 audio_encode=pcm_s16le / samplerate=16000 / lang） |
| 建连与握手 | 假服务端收到首帧前完成握手；错误凭据 → `AiUnavailable`（不重试 401） |
| 推流节拍 | 3200B 输入 → 假服务端按 1280B/40ms 收到 3 帧（假时钟推进） |
| cn.st 解析 | 多级 rt/ws/cw 嵌套 → 文本按正确顺序拼出；空数组不崩 |
| apd/rpl 透传 | 解析结果与 T1 assembler 的输入契约一致（pgs/rg/bg/ed 不丢字段） |
| final | 收到 final 包 → 输出 archive/final 事件且通道可安全 stop |
| 断开重连 | 服务端主动断开 → 按策略重连；超过上限 → `AiUnavailable` |
| stop 幂等 | 连续两次 stop 不报错；无残留任务（`asyncio.all_tasks` 断言） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/media/test_xunfei_ast.py` | 全绿 |
| 无凭据时的行为 | `start()` 抛出带 code 的配置错误（不静默用假数据） |

## 不做

- 不做本地 VAD/端点检测（由前端静音检测 + 用户按钮控制）；不做音频重采样（前端已给 16k PCM）；
  不做多路并发转写（单会话单通道，D15）。

