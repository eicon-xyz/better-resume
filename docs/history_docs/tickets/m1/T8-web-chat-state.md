# M1-T8 — chat 运行态与数据层（zustand + TanStack Query + controller-hook）

- blocking：M1-T5 M1-T6

## 目标

按 §5.5 的分工修正旧项目「服务端状态手工镜像进全局 store」的坏味道：
**TanStack Query 管服务端缓存，zustand 只管会话内运行态**，controller-hook 组装两者。

## 交付物

- `apps/web/src/chat/store.ts`（zustand）：`{ messages, streaming, activeRequestId, error }` +
  `actions: appendUser, appendAssistantChunk, appendReasoningChunk, finishAssistant, reset`
- `apps/web/src/chat/queries.ts`（TanStack Query）：`useConversations`、
  `useConversationHistory(sessionId, { before, limit })`、`useModels`；变更后 `invalidateQueries`
- `apps/web/src/chat/useChatStream.ts`（controller-hook）：发送 -> 建会话（无会话时先建后导航，
  照旧项目「先建会话再导航」的握手）-> SSE -> renderer -> store 更新 -> done 后 invalidate 历史
- `apps/web/src/chat/selectors.ts`：消息合并与去重（乐观 user 消息 + 服务端历史回填不重复）
- 测试（vitest + msw）：首次发送自动建会话并按序导航；reasoning-only 首帧不空转；
  切换会话丢弃在途 chunk；错误帧 -> store.error + 保留已收内容；历史回填去重

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 上述 5 类用例全绿 |
| `pnpm -C apps/web typecheck && pnpm -C apps/web lint` | exit 0 |
| 数据源唯一性 | store 里不出现服务端历史的副本（历史只从 Query 读） |

## 形态提议（待确认）

- Query key 带 `authEpoch`（用户名/会话变化即换代），但不引入 Redux（D05 砍 Redux）。
- 乐观更新只用于「用户消息」，assistant 内容一律由流写入 store（不做双写）。

## 不做

- 不做消息重发队列、不做离线草稿、不做多标签页同步。
