# M4-T9 — 假 adapter 驱动的端到端

- blocking：M4-T2 T5
- 纪律：这一票是**证据票**：先把端到端用例写红，再补齐让它绿

## 目标

在没有讯飞凭据、没有麦克风的 CI 里，仍能证明"音频进 → 文字出 → 进输入框 → 可提交"这条链路是通的：
后端用 `ScriptedTranscriptionChannel`（真 WS 端点、真 ticket、真 assembled 事件），
前端用假 WebSocket/MediaStream（真 store、真组件、真提交）。

## 交付物

- `tests/test_media_e2e.py`：`POST /auth/ws-ticket` → `websocket_connect` → 送 3 段 PCM →
  收到 `replace/archive/final` 序列 → 断言三级文本（可直接喂给面试答案框）
- `apps/web/src/audio/e2e.test.tsx`：假 getUserMedia + 假 WebSocket → 录音 → 转写上屏 →
  点提交 → 断言 `submitInterviewAnswer` 收到完整文本
- `apps/api/scripts/media_smoke.py`：可复跑的真机脚本（有凭据时连真讯飞 AST；无凭据时
  `--scripted` 跑本地通道 + 真 edge-tts 合成），打印事件序列与音频字节数

## 测试

| 用例 | 断言 |
| --- | --- |
| 后端 E2E | 事件序列 `replace → replace → archive`；最终 merged 文本 == 脚本预期；通道 stop 被调用 |
| 后端 E2E（票复用） | 同一张票第二路连接 4401 |
| 前端 E2E | textarea 出现完整转写；提交请求体一致；录音按钮回到 idle |
| 前端 E2E（错误路径） | WS 中途断开 → 保留已转写文本 + 可重试提示 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_media_e2e.py` | 全绿 |
| `pnpm -C apps/web test --run` | 全绿 |
| `uv run python scripts/media_smoke.py --scripted` | 打印事件序列 + 真 edge-tts mp3 字节数 |

## 不做

- 不用假数据冒充真机结论：本票产出的是**契约级证据**，真机结论只认 T10。

