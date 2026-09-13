# M4-T3 — WS 一次性 ticket + 转写端点

- blocking：M4-T1
- 纪律：先写失败测试（红），再实现（绿）

## 目标

把 D11 的"WS 握手一次性 ticket"从 M0 的占位落地，并提供转写 WebSocket：
HTTP 拿票（鉴权）→ WS 用票换 Principal（用后即焚）→ 二进制帧进通道 → 下行归一事件。

## 交付物

- `identity/tickets.py`：真实现 `WsTicketStore`（Redis 优先 / 内存回退，与 M0 的 session store 同构），
  票 = 随机 32B、TTL 30s、**一次性**（`consume` 原子删除）
- `identity/router.py`：`POST /api/v1/auth/ws-ticket`（需登录，返回 `{ticket, expires_in}`）
- `http/media.py`：
  - `WS /api/v1/media/transcribe?ticket=...`：无票/过期/复用 → 4401 关闭；成功 → `start(ctx)` →
    二进制帧 `feed()` → 通道事件转 JSON 下行（`{kind, text, seg_id, revision}`）→
    客户端 `stop`/断开 → `stop()`（幂等）
  - 单会话单通道（D15）；并发第二路 → 明确 4409 关闭
  - 心跳：服务端每 N 秒发 `{"kind":"ping"}`（可被 settings 关掉）
- `media/factory.py`：按 settings 选择 adapter（`xunfei` / `scripted`），缺凭据时启动即明确报错
- 测试：`tests/test_ws_ticket.py`、`tests/test_media_ws.py`（用 FastAPI 的 `TestClient.websocket_connect`）

## 测试

| 用例 | 断言 |
| --- | --- |
| 票据一次性 | 第一次连接成功；用同一张票第二次连接 → 4401 |
| 票据过期 | 假时钟推进 31s → 4401 |
| 未登录拿票 | 401 |
| 无票连接 | 4401（且不建立通道） |
| 音频帧 → 事件 | 送 2 帧 PCM → 收到 replace/archive 事件（scripted adapter） |
| 并发第二路 | 同一用户第二路连接 → 4409，第一路不受影响 |
| 断开清理 | 客户端断开 → 通道 `stop()` 被调用（断言 adapter 计数）、无残留任务 |
| 心跳 | 静默 N 秒收到 ping（可关） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_ws_ticket.py tests/test_media_ws.py` | 全绿 |
| OpenAPI | 新 HTTP 端点进契约（WS 不进 OpenAPI，文档里写明） |

## 不做

- 不做 WS 消息级鉴权重放保护（ticket 已是一次性）；不做多路复用/多设备会话（M6）；
  不做服务端 VAD（前端按钮控制开始/结束）。

