# conversation

## 职责

会话与消息的唯一归属（chat / interview 共用一张表 + JSONB 载荷），seq 原子分配。

## 对外接口

`SqlConversationStore`（`create` / `append` / `history` / `require_owner`）、`SessionRef`、`Message`。

## 不变量

1. 一条会话只属于一个 user_id；`require_owner` 失败一律 404（泄露存在性 = 越权探测）。
2. `seq` 在事务里递增，历史分页按 seq 游标（不用 offset），否则并发追加会跳消息/重复。
3. 流式回复即使失败也要落一条 assistant 消息（历史完整优先）。

## 已知陷阱

- `(session_id, client_message_id)` 唯一约束是幂等门禁：客户端重试同一 id 时返回既有的重复提示，
  不要写第二条用户消息（M1 的 dupe 用例锁着这条）。去重键不满足唯一语义前提时，该去重的地方会静默不去重（M3 P0）。
- 取消（客户端断开）路径要 `try/finally` + shield 写回，否则半截回答丢失（M1 的 `cancelled` 语义）。
- 前端因为一次限流清空过候选人输入：提交失败必须保留文本（M3 P10），后端语义别鼓励"重发新消息"。

## 测试地图

`tests/test_conversation_store.py`（seq 并发 20 次）、`tests/test_chat_service.py`、`tests/test_chat_api.py`。

## 常见变更配方

改消息字段：ORM → 迁移 → `Message` 模型 → `ChatMessageView` → 重生成 openapi/TS → 用例。
