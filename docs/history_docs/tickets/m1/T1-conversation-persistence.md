# M1-T1 — conversation 持久化（表 + store + seq 原子性）

- blocking：M0
- 纪律：先写失败测试（红），再实现（绿）

## 目标

把 §12.2 的 `ConversationStore` 从占位换成真实现：Postgres + JSONB，消息归属唯一，
seq 原子且连续，越权不可见。

## 交付物

- 迁移 `0002_conversations`：
  - `conversations(id uuid pk, kind text check in ('chat','interview'), user_id text, title text,
    model_ref text null, message_count int default 0, meta jsonb default '{}', created_at, updated_at)`
    索引：`(user_id, updated_at desc)`
  - `messages(id uuid pk, conversation_id fk on delete cascade, seq int, role text, content text,
    reasoning text null, token_count int null, error_message text null, meta jsonb default '{}',
    created_at)`；`unique(conversation_id, seq)`；`index(conversation_id, seq desc)`；
    `gin(meta jsonb_path_ops)`（对应 D03 的 JSONB + GIN）
- `better_resume/conversation/store.py`：`SqlConversationStore`（append / history / require_owner
  + `create` / `list_for_user` / `delete` / `update_title` / `increment_count`）
- `better_resume/conversation/errors.py`：`ConversationNotFound`、`ConversationForbidden`
- `better_resume/conversation/models.py`：补 `Conversation` 实体（不是 SessionRef 值对象）
- 测试（真 Postgres；连不上 skip）：JSONB 往返、`history(before, limit)` 游标分页、
  越权 -> 异常、删除级联、**并发 append 的 seq 唯一且连续**（`asyncio.gather(20)`）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run alembic upgrade head && uv run alembic check` | 无 drift |
| `uv run pytest -q tests/test_conversation_store.py` | 全绿（含并发 seq 用例） |
| 并发用例断言 | 20 个 append 的 seq 集合 == {1..20}，无重复 |

## 形态提议（待确认）

- seq 分配：`SELECT ... FOR UPDATE` 锁会话行 + `COALESCE(max(seq),0)+1`（同事务），
  唯一索引兜底重试一次；不引 Redis Lua（旧项目做法，D03 精神）。
- `require_owner` 越权统一抛 404（不泄露会话是否存在）。
- 软删除不做（M1 直接级联硬删）。

## 不做

- 不做 interview 会话的业务逻辑（只保证 kind 字段可用）；不做消息全文检索。
