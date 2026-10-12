# P14-T7 — 聊天页（并入页壳 + 会话侧栏二级化 + composer 复用）

- Status: ready-for-agent
- Blocked by: T3, T6
- 唯一写入路径：apps/web/src/pages/ChatPage.* 与 pages/chat/*（SessionSidebar / MessageList / Composer / MessageBubble）

> 依据 README §1.4 该页线框（逐块已获用户确认）、§1.5 视觉语言。纪律：先红后绿；测试只写带逻辑的缝；纯样式不写测试。
## 目标
按线框：并入页壳顶栏（模型选择保留在主区头或顶栏右侧）；会话侧栏 token 化（hover/active/选中态渐变边）为页内二级栏；消息气泡与 composer 复用面试间的新样式（消 3 处重复）；空态升级。
## 红-绿切片
| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 会话侧栏行为 | 选中会话高亮、切换行为既有测试全绿 |
| 2 | SSE 流式渲染不退化 | 光标/流式文本呈现既有测试全绿（blink 保留且有 reduced-motion） |
| 3 | 重复样式收敛 | badge/composer 的重复定义合并后守卫②④仍绿 |
## 红线
- 不改业务逻辑、数据流、REST 契约；不改路由。
- SSE 渲染与转写合并语义不许动。
- 视觉走 token（T2 的新 token），禁裸值（守卫②）；动画必须有 reduced-motion 处理（守卫④）。
## 验收
| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 既有例不红 + 本票行为单测（如有）绿 |
| `bash scripts/verify.sh --layer all` | 绿 |
| 前后对照截图 | 落 `docs/design/<页面>/`（线框 vs 实现） |
## 不做
设置页。