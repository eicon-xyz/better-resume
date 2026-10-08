# P8 提案：审计高危项硬化（5 条修复 + 3 条守卫）

> 依据：`docs/audit/` 的 122 条**设计评审**里挑出的 8 条候选，本轮**逐条本机实测复核**（判定表见 §1），
> 外加一条实测挖出、审计里没有的新发现（**N1 测试污染**）。
> 状态：**用户已确认**（2026-10-07）——范围 = 5 条修复 + 3 条便宜的守卫；IE-01 语义选定 **(b) 原地重评**；
> `media-04` 明确不碰（要先定方向）。
> 复核手法：3 个只读调查员（禁改仓库，复现物全在 `/tmp`）+ 本人在共享测试库上实跑；仓库零改动。

## 1. 现状盘点（实测，非文档口径）

| id | 判定 | 实测到的红 | 证据起点 |
| --- | --- | --- | --- |
| `conversation_chat-02` | ✅ 真（**症状纠正：不是 404**） | 201 条会话时 `POST /stream` = **200 + error 帧 `kind=unknown`**，消息不落库；`GET /messages` 同会话却 200 | `chat/service.py:171-179`；`conversation/store.py:61-72` |
| `IE-01` | ✅ 真 | 评分 504 后**同 `request_id`** 重试 = `201 + replayed=true + score=None`，分数永久拿不回；换新 id 对照 = `score=84.0` | `answer_service.py:118-121,371-377`；`answer_repo.py:58-67` |
| `web-04` | ✅ 真 | 连续两条**内容相同**的回答：第二条在 refetch 落地前被内容去重吞掉（选择器级 + ChatPage 级双红）；refetch 失败则永久不回 | `apps/web/src/chat/selectors.ts:40-41`；`ChatPage.tsx:69-72` |
| `identity_jobs-01` | ⚠️ 真（需两变量都设） | `sentinels=" , "` + master 非空 → 校验放行、`uses_sentinel=False`、普通 `ConnectionPool`、**无日志** | `settings/config.py:236-238` vs `redis_client.py:40-42,49-51` |
| `settings_observability-03` | ⚠️ 真（开关默认关） | `BR_RESILIENCE__DISTRIBUTED=true` → `GET /resilience/stats` **500**（`AttributeError`） | `main.py:107,109-117`；`distributed.py:274,291` |
| `resume_parser_db-03` | 🌱 潜伏 | 改 ORM 的 CHECK 文本 → `alembic check` **0 op**（盲）；插入新状态 → `CheckViolationError` | `orm.py:36-41` / `c28d77ba4f32:49-54` / `session_fsm.py:10-16` |
| `media-04` | ⚠️ 真，仅 `--scale ≥ 2` | 第二路 WS 落另一副本 → 排他被接受、双份供应商流；附带：真实 HTTP 下 4409 变 **403** | `registry.py:6-14`；`main.py:76`；`http/media.py:136-139` |
| `media-01` | 🎨 设计味道 | 两份映射**当前逐行等价**；用漂移副本替换 scripted → 6/6 **仍绿**（缺守卫，不是缺陷） | `xunfei_ast.py:283-293` vs `scripted.py:97-105` |

**N1（新发现，审计里没有）· 测试污染 → 子集运行假红**，因果链实跑闭合：

```text
[0] 重置默认                                   → chat=openai_compat:deepseek-flash
[1] 单跑 tests/test_scene_routing.py           → 绿（exit 0），但 chat 变成 xingyun:flow-chat   ← 污染者 :141,177 真 PUT 不还原
[2] 紧接着单跑 tests/test_chat_api.py          → 红：junit 8 tests / 6 failures（理由全是缺 XINGCHEN_API_KEY）
[3] 重置默认                                   → 恢复干净
```

全量为什么一直绿（实测连跑两遍 `865/0/0`、`865/0/0`）：`llm_gateway/test_scene_binding_store.py` 的
`factory` fixture 在 setup 时把**全表**重置为默认，且它排在 `test_chat_api.py` 之前。
→ **`verify.sh --layer all` 的绿掩盖了「只跑子集的人撞 6 条假红」**；审计读代码，读不到运行状态。

## 2. 目标（本轮范围）

**修复（5）**：N1 测试污染 · IE-01 · conversation_chat-02 · identity_jobs-01 · web-04
**守卫（3，便宜）**：so-03（开关打开即 500）· resume_parser_db-03（三份词表一致性断言）· media-01（跨适配器等价性守卫）

每条**先写会红的测试，再改实现**（垂直切片：一个用例红 → 最小实现绿 → 下一个）。

## 3. 方案（逐条）

### 3.1 N1 测试污染
- 缝：`tests/test_scene_routing.py` 自带的 autouse fixture 快照 + 还原 `llm_scene_bindings`；
  文件末尾加一条**同文件内**的确定性回归用例（前序用例切换过场景 → 断言表已回默认）。
- 证据口径：修前 `pytest tests/test_scene_routing.py tests/test_chat_api.py` 红；修后同一条命令绿。
- 不做：全局 autouse（会让所有用例依赖 DB，破坏"无 DB 时单测仍可跑"）。

### 3.2 IE-01（语义 = **b 原地重评**）
- 命中失败行（`error_message IS NOT NULL` / `score IS NULL`）时**不 replay**，而是走完整评分并**原地更新该行**；
  命中成功行仍走 replay（幂等语义不变）。
- 缝：`tests/interview_engine/test_answer_service.py` + HTTP 面 `tests/test_interview_answers_api.py`
  （"同 `request_id` 在失败后重试必须拿到分数"）。
- 行数不变 → 报告聚合与既有断言不受影响。

### 3.3 conversation_chat-02
- store 增加 `get_owned(session_id, user_id)`（复用既有 `_fetch` + 归属校验），`ChatService._load` 直接调用，
  删掉 `list_for_user(limit=200)` 线性查找。
- 缝：`tests/test_chat_service.py`（>200 会话时按 id 打开自己的会话）、`tests/test_chat_api.py`（SSE 正常出帧）。

### 3.4 identity_jobs-01
- 判据收敛到 `RedisTopology.from_settings`：解析不出**有效地址**即拒绝；`Settings` 的 validator 复用同一份，
  删掉 `bool(...strip())` 第二判据。
- 缝：`tests/test_settings.py` + `tests/test_redis_client.py`（`","` / `" , "` + master → 启动即拒）。

### 3.5 web-04
- `ChatMessage` 携带服务端 id（append 时为空、merge 时回填），去重按键不按内容。
- 缝：`apps/web/src/chat/selectors.test.ts` + ChatPage 级（prop 逐事件驱动那条路径）。

### 3.6 守卫三条
- **so-03**：定义含 `run/aclose/stats` 的协议并改 `main.py` 标注；`DistributedAiResilience.stats()` 委托 inner；
  缝 = `tests/test_resilience_api.py` 增加 `distributed=true` 用例。
- **词表一致性**：CHECK 文本从 `SessionStatus` 派生（迁移与 ORM 共用常量）**或**加一致性断言测试；
  缝 = `tests/test_migrations.py`（枚举 ↔ ORM 约束 ↔ DB `pg_get_constraintdef`）。
- **media-01**：把 `TranscriptUpdate→TranscriptEvent` 提成 media 层单一函数（适配器只喂包）+ 跨适配器差分测试；
  缝 = `tests/media/`。

## 4. 明确不做

- `media-04`（排他性挪 Redis vs 明确钉死单实例——**要先定方向**，属下一轮）。
- `media-01` 之外的语音适配器重构、`so-03` 引申的"后端引入类型检查门禁"（单独提案）。
- 审计台账里其余条目（本轮不铺开清台账）。

## 5. 交付物

- 代码 + 每条一个红-绿切片的小步提交（提交信息说 WHAT）。
- 本目录 `ACCEPTANCE.md`：可复跑命令 + 原始输出 + 数字 + **未验证项** + 与提案的偏差。
- `docs/audit/FIXES.md` 台账追加本轮条目。

## 6. 验收口径

1. 每条修复都有"修前红 → 修后绿"的**原始输出**（含命令原文）。
2. 收尾跑 `bash scripts/verify.sh --layer all`（15 条命令）全绿；后端 `--junitxml` 读数 0 failed 0 skipped；
   前端 `pnpm -C apps/web test --run` 全绿。
3. 未验证项必须写出来（不许拿"应该没问题"当证据）。
