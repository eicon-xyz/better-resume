# M6-T3 — 会话热态与跨实例恢复

- blocking：M6-T1
- 纪律：先写失败测试（红），再实现（绿）；**Postgres 仍是唯一真相，Redis 只是热层**

## 目标

kill 一个 api 实例后，另一个实例必须能继续同一场面试（题号、已答、分数、追问计数一致）。
M2 的 `restore` 已经能从 Postgres 派生视图，本票加的是：**热层缓存 + 来源标记 + 失效**，
并证明"跨实例恢复"这件事是可测的（不靠感觉）。

## 交付物

- `interview_engine/hot_state.py`：`HotStateStore`（Redis）
  - `get(session_id) -> SessionView | None`、`put(session_id, view, ttl)`、`invalidate(session_id)`
  - 写路径（答题/出题/结束）在事务提交后失效缓存（**先提交再失效**，避免脏读）
  - 视图带 `source: Literal["hot","derived"]`（对齐旧项目置信度思路，只保留两档）
- `restore_service.py`：先查热层（命中则 `source="hot"`），未命中走 DB 派生（`source="derived"`）并回填
- `settings`：`hot_state_ttl_seconds`（默认 600）、`hot_state_backend: memory|redis`
- 测试：`tests/test_hot_state.py`（≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 命中热层 | 第二次 restore 不再查 interview 表（SQL 计数断言），`source="hot"` |
| 失效 | 提交一次答题后再 restore → `source="derived"`，题号/分数是最新的 |
| TTL | 假时钟推进超 TTL → 回落到派生 |
| 跨实例 | 实例 A 写、实例 B 读（同一 Redis）→ 视图一致 |
| 一致性 | 热层与派生视图字段逐一相等（结构化 diff，不是快照字符串） |
| 缓存穿透 | 不存在的会话 → 404 且不写热层 |
| Redis 挂掉 | 记警告并全部回落派生（不阻塞业务） |
| 结束面试 | finish 后热层被替换为终态视图（`status=finished`） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_hot_state.py` | 全绿 |
| 回归 | M2 的 restore/report 用例在 `hot_state_backend=memory|redis` 下都绿 |

## 不做

- 不做旧项目那种字段级 patch/去抖合并（973 行服务的教训）；不做多级快照（热层只有一层）；
  不做跨实例的 SSE 连接迁移。

