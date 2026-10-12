# M1-T5 — 前端 api-client（唯一网络接缝）

- blocking：M1-T4

## 目标

§12.2 的 `createApiClient`：全站唯一网络出口——类型化端点 + POST-SSE 客户端 + 错误归一。

## 交付物

- `apps/web/src/api/client.ts`：`createApiClient({ baseUrl, onError })`
  - 基于生成的 `schema.d.ts` 的类型化端点（chat 会话 CRUD / 历史 / models / auth）
  - 统一解包与错误归一：HTTP 状态 -> `ApiError`（含 code/message/status/requestId），
    网络失败/超时/中止三类区分（照 `errors/index.ts` 的思路重写，不引 axios）
  - `credentials: "include"`（HttpOnly cookie，D11，前端不碰 token）
- `apps/web/src/api/sse.ts`：POST-SSE 客户端（`fetch` + `ReadableStream` + `AbortController`），
  逐帧解析 `event:`/`data:`、忽略心跳与脏帧、把 `done/error` 归一为结束回调
- 测试（vitest + fetch mock）：端点类型化调用、错误映射表、超时/中止、SSE 分帧跨 chunk 拼接、
  脏帧丢弃、`AbortController` 后不再回调

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 新增用例全绿 |
| `pnpm -C apps/web typecheck` | exit 0（端点入参/出参都由生成类型约束） |
| 覆盖 `parseAiStreamChunk` 的历史坑 | 一个 chunk 含多帧、一帧跨两 chunk、reasoning 与 content 交错 |

## 形态提议（待确认）

- 不引 axios/fetchEventSource：浏览器原生 `fetch` + `ReadableStream` 足够，少两个依赖（Q2 相关）。
- 请求去重（旧 `RequestPolicy`）M1 只做「同 key 在途复用」最小版，防重复计费的重活交给
  端点自身的幂等键（T3 的 client_message_id）。

## 不做

- 不做鉴权 token 管理（cookie 自动携带）、不做离线队列、不做重试风暴控制（M3 后端侧统一治理）。
