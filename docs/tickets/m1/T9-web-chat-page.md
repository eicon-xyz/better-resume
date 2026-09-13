# M1-T9 — chat 页面（打字机 + reasoning 面板 + 历史回放）

- blocking：M1-T7 M1-T8

## 目标

M1 的对外验收物：一个能演示「打字机对话 + reasoning 分流 + 历史回放」的页面。

## 交付物

- 路由（react-router）：`/` -> 重定向 `/chat`；`/chat/:sessionId?` -> ChatPage
- `ChatPage`：会话侧栏（我的会话列表 + 新建）、消息流、输入区（Enter 发送 / Shift+Enter 换行）、
  模型选择（`/models` 里 enabled 项）、空态与错误态
- **打字机**：assistant 内容经 T6 renderer 逐字上屏，流式中显示光标，结束后移除
- **reasoning 面板**：`reasoning` 非空时渲染「深度思考」折叠面板（流式时自动展开、完成后可收起；
  仅 reasoning 无 content 时面板内显示进行中状态）
- **历史回放**：进入 `/chat/:id` 时用 Query 拉历史（seq 倒序分页 -> 正序渲染），
  上滑加载更早消息；刷新后内容与流式结束时一致（含 reasoning）
- 未登录时展示 dev 会话入口（调用 M0 的 `POST /api/v1/auth/session`，Q3），登录后进入 chat
- Markdown 渲染：`react-markdown` + `remark-gfm`（代码块高亮留 M2，Q6）
- 测试（vitest + msw）：打字机逐帧上屏、reasoning 折叠交互、历史回放渲染、发送中断（Abort）
  后状态可恢复、空态/错误态

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 页面级用例全绿 |
| `pnpm -C apps/web build` | 构建成功 |
| 手工演示（截图/录屏） | ① 打字机逐字输出 ② reasoning 面板分流 ③ 刷新后历史回放一致 |
| 真机联通 | compose 起三服务 + 本地 `BR_DEEPSEEK_API_KEY` 时能真实对话（无 key 时展示诚实错误） |

## 形态提议（待确认）

- 动效只用 CSS（光标闪烁、面板展开），不引 framer-motion（Q6）。
- 移动端只保证可用（不断点设计），M1 不做响应式打磨。

## 不做

- 不做多模态、不做语音播报（TTS 归 M4）、不做消息编辑/重新生成（M2 再评估）。
