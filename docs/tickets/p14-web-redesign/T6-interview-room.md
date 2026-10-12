# P14-T6 — 面试间（房间二级行 + 问题卡升级 + composer 卡片化）

- Status: ready-for-agent
- Blocked by: T3
- 唯一写入路径：apps/web/src/pages/InterviewRoomPage.* 与 pages/interview/RoomParts.*

> 依据 README §1.4 该页线框（逐块已获用户确认）、§1.5 视觉语言。纪律：先红后绿；测试只写带逻辑的缝；纯样式不写测试。
## 目标
按线框重排：页壳顶栏 + 房间二级行（进度步骤条「题 2/5」+ 类别徽章 + 结束按钮）；问题卡题面大字号、focus_points 标签化、类别徽章渐变点缀；反馈按时间分组、最新一条高亮；composer 卡片化（字数计数、语音按钮态变化、快捷键提示）；<1024 上下堆叠、反馈折叠、composer 吸底。
## 红-绿切片
| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 答题流不退化 | 提交/追问/下一题的既有行为测试全绿（含转写合并语义） |
| 2 | 反馈分组 | 最新反馈高亮态与既有反馈数据顺序一致 |
| 3 | composer 行为等价 | 字数计数与提交按钮启用逻辑由既有状态驱动 |
## 红线
- 不改业务逻辑、数据流、REST 契约；不改路由。
- **转写合并语义是红线中的红线**（AGENTS.md：三层合并、调用点清零）——本票只动视觉层，VoiceWiring/转写相关测试必须全绿。
- 视觉走 token（T2 的新 token），禁裸值（守卫②）；动画必须有 reduced-motion 处理（守卫④）。
## 验收
| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 既有例不红 + 本票行为单测（如有）绿 |
| `bash scripts/verify.sh --layer all` | 绿 |
| 前后对照截图 | 落 `docs/design/<页面>/`（线框 vs 实现） |
## 不做
聊天页 composer（T7 复用本票样式）；业务逻辑。