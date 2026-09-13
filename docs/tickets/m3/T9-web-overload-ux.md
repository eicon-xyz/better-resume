# M3-T9 — 前端：429/503/504 归一与"服务繁忙"体验

- blocking：M3-T8
- 纪律：先写失败测试（红），再实现（绿）；只 mock 网络边界

## 目标

后端现在会明确说"忙/熔断/超时"（429/503/504 + kind），前端不能再把它们显示成"服务器错误"。
本票把这三类归一进 ApiError，并让聊天页与面试房间给出可操作提示。

## 交付物

- src/api/errors.ts：ApiErrorKind 增 rate_limited / unavailable / gateway_timeout；
  kindForStatus 映射 429/503/504；解析 Retry-After（秒数与 HTTP-date）到 ApiError.retryAfterSeconds
- src/api/client.ts / sse.ts：SSE 的 error 帧同样归一（后端已带 kind）
- src/pages/ChatPage.tsx：429/503 时显示"服务繁忙，N 秒后可重试"提示条 + 重试按钮
  （复用已有 store 的运行态，不新建状态源）；504 提示"上游超时，请重试"
- src/pages/InterviewRoomPage.tsx：评分/追问遇 429/503/504 时不丢答案（保留输入框内容），
  提示可重试并说明分数未记录（与后端幂等/回滚语义一致）
- 测试：errors.test.ts 扩充（状态码映射 + Retry-After 解析）、ChatPage/房间页各一个失败态用例

## 测试

| 用例 | 断言 |
| --- | --- |
| 状态码映射 | 429 → rate_limited、503 → unavailable、504 → gateway_timeout；原有 401/403/404/409/422/500 不变 |
| Retry-After | 秒数与 HTTP-date 两种形式都能解析；缺失时为 null |
| 聊天页 429 | 出现"服务繁忙"提示与重试按钮；点击后重新发起同一请求 |
| 房间页 503 | 答案文本还在输入框；提示"未记录分数，可重试" |
| 说明文案 | 不出现"未知错误"（有 kind 就必须有对应文案） |

## 验收

| 命令 | 期望 |
| --- | --- |
| pnpm --filter web test --run | 全绿（104 → 更多） |
| pnpm --filter web lint / tsc --noEmit | 0 warning / 0 error |
| pnpm run check:api | apps/web/src/api/schema.d.ts 与 openapi.json 一致 |

## 不做

- 不做自动重试队列/退避策略（用户手动重试，避免"静默重放"）；不做离线缓存；
  不做全局 toast 系统（只在既有页面加提示条）。

