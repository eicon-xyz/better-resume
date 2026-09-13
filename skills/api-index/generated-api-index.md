# 生成的 API 索引（勿手改）

> 由 apps/api/scripts/extract_api_index.py 从 apps/api/openapi.json + apps/web/src/App.tsx 生成；
> CI 用 --check 拦截漂移。改动端点或路由后请重新生成并提交。

端点总数：24（另有 WebSocket 1 条）

## 端点（apps/api/openapi.json）

| 方法 | 路径 | 说明 | 权限 | 幂等语义 | 前端消费点 |
| --- | --- | --- | --- | --- | --- |
| GET | /api/v1/auth/me | Me | 需登录 | 天然幂等 | `api/client.ts` |
| DELETE | /api/v1/auth/session | Delete Session | 公开 | 天然幂等 | `api/client.ts` |
| POST | /api/v1/auth/session | Create Session | 公开 | 非幂等 | `api/client.ts` |
| POST | /api/v1/auth/ws-ticket | Create Ws Ticket | 公开 | 非幂等 | `api/client.ts` |
| GET | /api/v1/chat/sessions | List Sessions | 需登录 | 天然幂等 | `api/client.ts` |
| POST | /api/v1/chat/sessions | Create Session | 需登录 | 非幂等 | `api/client.ts` |
| DELETE | /api/v1/chat/sessions/{session_id} | Delete Session | 需登录 | 天然幂等 | `api/client.ts` |
| PUT | /api/v1/chat/sessions/{session_id} | Rename Session | 需登录 | 天然幂等 | `api/client.ts` |
| GET | /api/v1/chat/sessions/{session_id}/messages | List Messages | 需登录 | 天然幂等 | `api/client.ts` |
| POST | /api/v1/chat/sessions/{session_id}/stream | Stream Reply | 需登录 | 幂等键 client_message_id | `api/client.ts` |
| GET | /api/v1/interview/sessions | List Sessions | 需登录 | 天然幂等 | `api/client.ts` |
| POST | /api/v1/interview/sessions | Create Session | 需登录 | 非幂等 | `api/client.ts` |
| POST | /api/v1/interview/sessions/{session_id}/answers | Submit Answer | 需登录 | 幂等键 request_id | `api/client.ts` |
| POST | /api/v1/interview/sessions/{session_id}/finish | Finish Interview | 需登录 | 幂等（报告冻结后回放快照） | `api/client.ts` |
| POST | /api/v1/interview/sessions/{session_id}/questions | Generate Questions | 需登录 | 幂等（已出题回放；生成中 409） | `api/client.ts` |
| GET | /api/v1/interview/sessions/{session_id}/report | Get Report | 需登录 | 天然幂等 | `api/client.ts` |
| GET | /api/v1/interview/sessions/{session_id}/restore | Restore Session | 需登录 | 天然幂等 | `api/client.ts` |
| POST | /api/v1/media/tts | Synthesize Speech | 需登录 | 非幂等 | `api/client.ts` |
| GET | /api/v1/media/tts/{digest}.mp3 | Get Speech | 需登录 | 天然幂等 | — |
| GET | /api/v1/models | List Models | 公开 | 天然幂等 | `api/client.ts` |
| GET | /api/v1/resilience/stats | Resilience Stats | 需登录 | 天然幂等 | — |
| GET | /api/v1/scenes | List Scenes | 需登录 | 天然幂等 | `api/client.ts` |
| PUT | /api/v1/scenes/{scene} | Update Scene | 需登录 | 天然幂等 | `api/client.ts` |
| GET | /healthz | Healthz | 公开 | 天然幂等 | — |

## WebSocket（不进 OpenAPI，单独维护）

| 协议 | 路径 | 说明 | 权限 | 幂等语义 | 前端消费点 |
| --- | --- | --- | --- | --- | --- |
| WS | /api/v1/media/transcribe | 实时转写（一次性 ticket 握手） | ticket | 握手票据一次性 | `audio/useTranscription.ts` |

## 前端路由（apps/web/src/App.tsx）

| 路由 | 页面组件 | 定义处 |
| --- | --- | --- |
| / | Navigate -> /chat | `apps/web/src/App.tsx` |
| /chat | ChatPage（pages/ChatPage.tsx） | `apps/web/src/App.tsx` |
| /chat/:sessionId | ChatPage（pages/ChatPage.tsx） | `apps/web/src/App.tsx` |
| /settings/ai | AiSettingsPage（pages/AiSettingsPage.tsx） | `apps/web/src/App.tsx` |
| /interview | InterviewIntroPage（pages/InterviewIntroPage.tsx） | `apps/web/src/App.tsx` |
| /interview/room/:sessionId | InterviewRoomPage（pages/InterviewRoomPage.tsx） | `apps/web/src/App.tsx` |
| /interview/report/:sessionId | InterviewReportPage（pages/InterviewReportPage.tsx） | `apps/web/src/App.tsx` |
| * | Navigate -> /chat | `apps/web/src/App.tsx` |

## 读法

- **权限**：需登录 = 会话 cookie；公开 = 见脚本里的 PUBLIC_PATHS；ticket = WS 一次性票据。
- **幂等语义**：GET/PUT/DELETE 天然幂等；POST 的幂等键由请求体字段推出（request_id、client_message_id 是入库去重键，同键重放返回既有结果）；
  状态机写操作按 FSM 语义标注（回放或 409，不会重复落库）。
- **前端消费点**：apps/web/src 下引用该路径的源文件（不含测试与生成的 schema.d.ts）；
  — 表示没有路径字面量，可能通过响应里的 url 字段间接使用。
