# M2-T8 — 面试房间（题目流 + 答题 + 反馈 + 追问标记 + 恢复）

- blocking：M2-T7
- 纪律：先写失败测试（红），再实现（绿）

## 目标

`/interview/room/:sessionId`：题目流为主轴——展示当前题 → 作答 → 评分反馈 → 追问或下一题 →
结束。支持刷新/断线恢复（restore）与「先答题后恢复」的竞态。

## 交付物

- `src/interview/roomStore.ts`（zustand）：`{ turns, currentQuestion, status, submitting, error }` +
  `applyTurnResult(result)`（把评分/追问/推进一次打补丁，对齐旧 useInterviewProgressState 的
  `applyProgressPatch` 思路，但只保留一个 reducer 入口）
- `src/interview/useInterviewRoom.ts`（controller-hook）：答题提交（`requestId` 幂等 +
  防双击 250ms 去抖）、追问标记、下一题、结束面试、restore 挂载
- 组件：`QuestionCard`（题号 + 考察点）、`AnswerComposer`（文本答题，M4 接语音转写）、
  `FeedbackCard`（分数 + 反馈 + 缺失要点）、`FollowUpBadge`（`3-F1` 标记 + 追问原因）
- 进度条：已答题数/总题数 + 当前阶段（asking/evaluating/follow_up）
- 测试（msw）：正常一轮（题→答→反馈→下一题）、追问一轮（`3-F1` 与原因展示）、
  重复提交只发一次请求、刷新后 restore 回到同一题、提交失败可重试且不重复计费

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 上述 5 类用例全绿 |
| `typecheck` / `lint` | exit 0 |
| 真实演示 | 完整答完 5 题（含至少 1 次追问）并结束 |

## 形态提议（待确认）

- 运行态只进 zustand；题目/答案的服务端状态留在 Query（房间页只读取一次并交给 store 管一局）。
- 打字机只用于 AI 反馈文案（复用 M1 的 stream-renderer），题目与分数直接渲染。

## 不做

- 不做语音、不做摄像头/神态（D09 砍）、不做草稿板（D09 砍）。
