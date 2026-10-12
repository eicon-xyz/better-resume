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

## 实测记录（2026-09-13）

同源链路端到端（Vite dev server 代理 → FastAPI → 真实 DeepSeek）：

```
login=200  建会话=ok  frames: content=25 reasoning=12 done=1
ANSWER : 栈是一种后进先出（LIFO）的线性数据结构，只允许在同一端进行插入和删除操作。
HISTORY: [(1,'user',10,reasoning=False,client_message_id='e2e-1'), (2,'assistant',39,reasoning=True)]
```

实现要点：

- 路由 `/` 重定向 `/chat`；`/chat/:sessionId?` 同一页面组件（新增/切换会话就是改 URL）。
- 历史回放走 `useInfiniteQuery` 的 seq 游标（每页 50，页内升序、页间倒序拼装），
  「加载更早的消息」按钮触发 `fetchNextPage`。
- reasoning 面板默认展开（流式时就是「显示思考」），折叠是每条消息各自的用户选择——
  为此去掉了原先的 `useEffect + setState`（React 19 的 `set-state-in-effect` 会告警）。
- 路由切换重置运行态，但**不会**重置刚创建的会话（send 里已经 openSession，避免把乐观消息清掉）。
- 踩坑：本地冒烟一开始打到了 **compose 里旧镜像**（端口 8000），导致 chat 端点 404——
  `BR_WEB_API_TARGET` 是给 dev 代理用的目标，默认 127.0.0.1:8000；对接本地 uvicorn 时要用
  `BR_WEB_API_TARGET=http://127.0.0.1:<port>`。compose 镜像需 `docker compose up -d --build` 才含 M1 代码。

## 不做

- 不做多模态、不做语音播报（TTS 归 M4）、不做消息编辑/重新生成（M2 再评估）。
