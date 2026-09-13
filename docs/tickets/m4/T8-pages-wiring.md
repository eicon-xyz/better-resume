# M4-T8 — 页面接线：语音答题 + 题目播报 + 对话语音输入

- blocking：M4-T6 T7
- 纪律：先写失败测试（红），再实现（绿）

## 目标

把 T5–T7 的三件套接到真实页面：面试房间"点麦克风说答案 → 实时上屏 → 提交"，
题目卡片"朗读"，对话页输入框"语音输入"。

## 交付物

- `pages/interview/RoomParts.tsx`：麦克风按钮（开始/停止 + 录音时长 + 实时 live 文本预览）、
  朗读按钮、权限错误与 WS 错误的可见提示（复用 M3 的 `describeApiError` 文案口径）
- `pages/interview/InterviewRoomPage.tsx`：离开页面/提交时停止录音（不泄漏麦克风）
- `pages/chat/Composer.tsx` + `ChatPage.tsx`：语音输入按钮与同一 store 绑定
- `api/client.ts`：`createWsTicket()`（新端点）+ 类型再生
- 测试：两个页面各 ≥3 例（录音→上屏→提交、权限拒绝提示、离开页面释放）

## 测试

| 用例 | 断言 |
| --- | --- |
| 语音答题 | 点麦克风 → live 文本进 textarea → 点提交 → 请求体里是转写后的完整文本 |
| 权限拒绝 | getUserMedia reject → 提示"未获得麦克风权限"，不进入录音态 |
| WS 断开 | 连接失败 → 提示可重试；已转写文本保留 |
| 离开页面 | 路由切换 → `track.stop()` 被调用（假 MediaStream 断言） |
| 题目朗读 | 点朗读 → ttsClient 被调用一次；播放中再点 → 停止 |
| 对话页语音 | 同一 store 的转写出现在对话输入框 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 全绿 |
| `pnpm -C apps/web build` | 通过（含 AudioWorklet 资源的打包路径） |
| `pnpm -C apps/web check:api` | schema.d.ts 与后端一致 |

## 不做

- 不做"按住说话"（点击开始/停止更适合长回答）；不做键盘快捷键冲突处理（Ctrl+Enter 已有）；
  不做语音提交（提交仍是显式按钮，避免误提交）。

