# M1-T3 — chat 后端 API：会话 CRUD + 历史 + SSE 流式 + 心跳

- blocking：M1-T1 M1-T2
- 纪律：先写失败测试（红），再实现（绿）

## 目标

§7.2 的 SSE 编排落到后端：取历史 -> 存用户消息 -> 流式生成 -> 全量存 assistant 消息（含
reasoning）-> done；错误也落一条 assistant 消息，保证历史完整（旧项目
ConversationStreamingSupport 的经验）。

## 交付物

- `better_resume/chat/service.py`：`ChatService.stream_reply(...)`（编排；调用点走
  `AiResilience.run()` 接缝，M1 的 AiResilience 是**直通实现**，单飞/熔断留 M3）
- `better_resume/http/chat.py`：
  - `POST /api/v1/chat/sessions`（建会话，可选 model_ref）
  - `GET /api/v1/chat/sessions`（我的会话分页）
  - `GET /api/v1/chat/sessions/{id}/messages?before=&limit=`（seq 游标历史，回放用）
  - `POST /api/v1/chat/sessions/{id}/stream`（**SSE**：`event: content|reasoning|meta|done|error`）
  - `PUT /api/v1/chat/sessions/{id}`（改标题）、`DELETE /api/v1/chat/sessions/{id}`
- SSE 细节：每 15s 心跳注释帧（`: ping`）、`X-Request-Id` 贯穿、客户端断开即取消上游流、
  `Cache-Control: no-cache`、`X-Accel-Buffering: no`
- 幂等：请求体带 `client_message_id`，同会话内重复投递只落一条 user 消息（唯一索引兜底）
- `better_resume/ai_resilience/passthrough.py`：`DirectAiResilience`（M3 替换为真策略）
- 测试（mock 网关边界 + 真库）：事件序列与顺序、reasoning 与 content 分流、错误事件 + 落库、
  心跳帧、取消传播、越权 404、幂等重复投递、历史分页回放

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_chat_api.py` | 全绿（网关用假实现，Postgres 真库） |
| `curl -N -X POST localhost:8000/api/v1/chat/sessions/{id}/stream` | 依次收到 `event: content` 帧与 `event: done` |
| 断开客户端 | 服务端日志出现取消记录，assistant 消息仍按已收内容落库 |

## 形态提议（待确认）

- 端点用 `POST .../stream`（不是 `.../chat`），语义更直白；SSE 事件名与 §12.2 的
  StreamEvent 一一对应（content/reasoning/done/vendor_meta/error）。
- 会话标题默认取首条用户消息前 30 字（不让 LLM 起标题，省一次调用，Q10）。
- 单条消息内容上限（如 8k 字符）在 API 层校验，防止超长注入 payload。

## 实测记录（2026-09-13，真实模型端到端）

`uvicorn` + 真 DeepSeek + 真 Postgres，`curl -N` 抓到的帧统计：
`41 event: content` / `12 event: reasoning` / `1 event: meta` / `1 event: done`；
历史回放 `[(1,'user',13),(2,'assistant',75,reasoning=True,token_count=151)]`。

实现要点（与原提案的差异）：

- **取消落库要处理两条路径**：任务被 cancel（CancelledError）与消费者提前关闭生成器
  （GeneratorExit）都会中断流；只捕 CancelledError 会漏掉后者 → 改为 `try/finally` +
  `persisted` 标志，`_persist_aborted()` 用 shield 保证半截答案落库（error_message="cancelled"）。
- **心跳不能取消上游**：SSE 用「生产者任务 + 队列」拆开，`asyncio.wait_for(queue.get(), 心跳)`
  超时只发 `: ping`，绝不 cancel 正在跑的模型流。
- **未配置密钥时不假装能跑**：`POST .../stream` 直接 503 并说明缺哪个环境变量。
- 会话归属错误统一 404（不泄露存在性），seq 冲突 409。

## 不做

- 不做断线自动重连与「续传」；不做多会话并行流的服务端串行化（M3 单飞覆盖）。
