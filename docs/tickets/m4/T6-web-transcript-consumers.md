# M4-T6 — 三级文本消费（一个 hook，两个输入框）

- blocking：M4-T5
- 纪律：先写失败测试（红），再实现（绿）

## 目标

D15「一个转写通道、两个消费方」：同一份三级文本同时服务面试答案框与对话输入框；
消费语义统一为「live 覆盖尾部、final 固化前缀」。

## 交付物

- `src/audio/transcriptStore.ts`（zustand，只放运行态）：`{live, final, merged, status, error}` +
  `applyEvent(event)`（replace → 覆盖 live；archive → final 追加、live 清空）
- `src/audio/useTranscriptBinding.ts`：把 `merged` 与本地输入框文本合并——
  规则：**只在用户光标位于末尾且本地文本是 merged 的前缀时追加**，否则只高亮提示"有新的转写"
  （避免覆盖用户手打的字）
- 接线：`pages/interview/RoomParts.tsx` 的 `AnswerComposer`、`pages/chat/Composer.tsx`
  各加一个"语音输入"按钮（录音中显示波形/计时 + 停止），文本进同一个 textarea
- 测试：`transcriptStore.test.ts` + 两个组件用例（含"用户正在打字时不覆盖"）

## 测试

| 用例 | 断言 |
| --- | --- |
| replace 覆盖 live | merged = final + live；final 不变 |
| archive 固化 | live 清空、final 追加；merged 与 archive 文本一致 |
| 打字中不覆盖 | 用户已输入 "我负责"，转写到达时 textarea 文本不变，出现提示 |
| 光标在末尾且为前缀 | 自动追加，不重复已有前缀 |
| 停止录音 | 状态回 idle，merged 保留（可继续编辑/提交） |
| 两个消费方 | 面试答案框与对话输入框绑定同一 store（同一事件两处都可见） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 全绿 |
| 交互 | 不做"边说边提交"；提交语义仍走既有按钮与幂等 requestId |

## 不做

- 不做标点/顺滑后处理；不做多段编辑历史（撤销由 textarea 原生支持）；不做草稿板（D09）。

