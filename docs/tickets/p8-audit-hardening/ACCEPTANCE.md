# P8 验收包：审计高危项硬化（5 修复 + 3 守卫）

> 状态：**待用户验收**（AI 不自行宣布完成、未推送、未合并、未删分支）
> 分支：`p8/audit-hardening`，从 `main` = `d1b764c` 切出
> 提案与实测判定表：`docs/tickets/p8-audit-hardening/README.md`（§1 的 8 条候选逐条实测）
> 复核手法：3 个只读调查员（复现物在 /tmp，仓库零改动）+ 本人在共享测试库上实跑。

## 0. 一句话

用户确认范围内 **5 条修复 + 3 条守卫全部完成**，每条都有「修前红 → 修后绿」的原始输出；
过程中发现并修掉一个**连带缺陷**（重试再次失败会撞唯一约束）与**两条自己引入的回归**（见 §5）。

## 1. 逐条证据（红 → 绿）

| # | 条目 | 缝（测试） | 修前（原始输出要点） | 修后 |
| --- | --- | --- | --- | --- |
| 1 | **N1 测试污染** | `tests/test_scene_routing.py` 新增回归用例 + conftest 快照还原 | `pytest tests/test_scene_routing.py tests/test_chat_api.py` = **14 tests / 7 failed**；新用例 `AssertionError: chat was left on xingyun:flow-chat` | 同一条命令 **14 / 0**（单文件 6 / 0） |
| 2 | **IE-01** | `tests/interview_engine/test_answer_service.py` + `tests/test_interview_answers_api.py` | `replayed=True`（断言 a failed attempt must not be replayed as a finished answer）；HTTP 面同 `request_id` 重试 = 201 + `score=None` | **20 tests / 0** |
| 3 | **conversation_chat-02** | `tests/test_chat_service.py`（+ `test_chat_api.py` / `test_conversation_store.py`） | `ConversationNotFoundError`（201 条会话时找不到第 201 条） | **27 tests / 0** |
| 4 | **identity_jobs-01** | `tests/test_settings.py` | 三个分隔符值全部 `DID NOT RAISE ValidationError`（`,` / ` , ` / ` , , `） | **39 tests / 0**（含 redis_client / distributed_flight / identity） |
| 5 | **settings_observability-03** | `tests/test_resilience_api.py` 新增 distributed=true 用例 | `AttributeError: 'DistributedAiResilience' object has no attribute 'stats'`（真 app + 真 PG/Redis + 真登录） | **117 tests / 0** |
| 6 | **resume_parser_db-03（守卫）** | `tests/test_migrations.py` | 守卫 + **变异证明**：`bash scripts/verify_mutation.sh` → 基线绿 → 变异红 → 恢复绿（sha256 与 HEAD 一致） | **2 tests / 0** |
| 7 | **media-01（守卫）** | `tests/media/test_event_map.py` | 抽取前：两份逐行等价且**无守卫**（调查员实证：用漂移副本替换 scripted → 6/6 仍绿） | 抽取后规则只有一份 + 源码警报 → **79 tests / 0** |
| 8 | **web-04** | `apps/web/src/chat/selectors.test.ts` | `Tests 1 failed | 5 passed`（第二条相同回答被内容去重吞掉） | 前端 **177 passed**、eslint + tsc 干净 |

## 2. 每条改了什么（一句话）

1. **N1**：`test_scene_routing.py:177` 真 PUT 切场景后不还原 → 共享测试库留下 `chat=xingyun:flow-chat`，之后**单跑** `test_chat_api.py` 必 6 红。改为 conftest 快照/还原 fixture（模块级 `usefixtures`），并加一条同文件内、确定性顺序的回归用例。
2. **IE-01**：失败的答案行占用成功幂等键 → 同 `request_id` 重试拿到 201 + `score=None`，分数永久拿不回。按**(b) 原地重评**：命中失败行不 replay，走完整评分并**原地覆写该行**（`AnswerRepository.overwrite`）；重试**再次失败**也走同一条行（否则撞唯一约束 —— 修的时候发现的连带缺陷）。
3. **chat-02**：`ChatService._load` 用 `list_for_user(limit=200)` 线性找自己的会话 → 超 200 条的老用户打开旧会话拿到 200 + SSE error 帧。改为 store 新增 `get_owned(session_id, user_id)`（一次查询同时完成归属校验与取行）。
4. **identity_jobs-01**：`BR_REDIS_SENTINELS` 的「成对且可用」有两份判据 —— `bool(strip())` 与「过滤空项后非空」。分隔符值（`,`）过校验后静默退回单节点、**无日志**。判据收敛到 `parse_sentinel_addresses`（settings 拥有一份，redis_client 复用）。
5. **so-03**：`main.py` 用 `resilience: object` 抹掉类型，包装类 `DistributedAiResilience` 缺 `stats()` → 打开分布式开关后 `/resilience/stats` 必 500。补 `stats()` 委托 inner，并新增 `AiResilienceSnapshot` 协议用于装配点标注。
6. **db-03**：会话状态词表三份拷贝（StrEnum / ORM CheckConstraint / 迁移 CHECK），而 `alembic check` 对 CHECK 文本完全盲（实测 0 op）。ORM 侧改为由 `SessionStatus` 派生；新增一条从 Postgres 读回 `pg_get_constraintdef` 的一致性断言，并用变异证明它真会咬。
7. **media-01**：assembler→事件 的映射在 `xunfei_ast` 与 `scripted` 里逐行重复。抽成 `media/event_map.py` 的 `TranscriptEventMapper`（规则与它的记忆同处一地），两个适配器只喂包；补多句切片用例 + 「适配器里不许再出现第二份」的源码警报。
8. **web-04**：`mergeHistory` 用「回答内容相等」去重 → 连续两条相同回答的第二条被静默吞掉（refetch 失败则永久不回）。改为**按回答所属那一轮的 `client_message_id` 去重**（内容比较只留作「没有前序用户轮」时的兜底）。

## 3. 全量收口

（见 §3.1 数字，最终由本条命令产出）

```bash
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer all      # 15 条命令
pnpm -C apps/web test --run             # 前端
python3 scripts/verify_audit_evidence.py --strict
```

### 3.1 数字（本次实测）

| 项 | 基线（本轮开工前） | 现在 |
| --- | --- | --- |
| `verify.sh --layer all` | ALL PASS（15 条命令，1m41s） | （待填） |
| 后端 pytest（带 BR_*） | 865 passed / 0 failed / 0 skipped | （待填） |
| 后端 pytest（不导出 BR_*） | 729 passed / **136 skipped** | （待填） |
| 前端 vitest | 175 passed | （待填） |

## 4. 未验证项（诚实清单）

1. **media-04 未修**（用户确认不做）：跨副本单通道排他在 `--scale api=2` 下仍失效；
   附带发现（真实 HTTP 下 pre-accept 的 4409 被 uvicorn 变成 **403**、前端 grep 零命中）也**未修**。
2. **so-03 的协议是文档级约束**：后端没有 mypy/pyright 门禁，所以「下次再包一层忘了 stats」不会在 CI 变红；
   真正拦住它的是新加的那条 distributed=true 用例。
3. **media-01 的等价证明是结构性的**（两份实现合并成一份 + 源码警报），不是「两个适配器逐帧对拍」；
   `paraformer_rt.py` 是同一规则的第三份实现（按供应商 sentence_end 驱动、不经 assembler），**未动**。
4. **identity_jobs-01 只收敛了一处判据**：地址**语法**仍在 `redis_client._sentinel_address`（`x:abc` 会抛，实测确认），未合并进 settings。
5. **N1 的还原 fixture 加在唯一已知污染者上**（`test_scene_routing.py` + conftest 共享 fixture），没有做全局 autouse —— 那会让所有用例强依赖数据库。
6. **前端只有选择器级证据进仓库**；页面级复现（真 ChatPage + 假 client）是调查员在 /tmp 做的，未进测试套件。
7. **IE-01 的修法选 (b) 原地重评**，因此「幂等」语义变成「同键可重入直到成功」——这是用户拍板的选择，已写进票据。
8. 真机/浏览器未复跑：本轮**零**真机调用（`--layer real` 未跑）。

## 5. 与提案的偏差，以及过程中发现的问题

### 5.1 三处执行偏差（提案 → 实际）

1. **media-01**：提案写「抽单一函数 + 跨适配器差分测试」；实际 = 抽取 `TranscriptEventMapper` + 单元守卫 + 源码警报。
   理由：合并成一份后「两个适配器对拍」不再有独立对象，改为证明「规则只有一份、且多句切片被钉住」。
2. **web-04**：提案写「`ChatMessage` 带服务端 id」；**做不到** —— SSE 的 `done` 帧只带 `finish_reason`，
   要让草稿拿到服务端 `seq` 得改传输协议。改为按「回答所属那一轮的 `client_message_id`」去重，效果等价且不动协议。
3. **so-03**：提案写「把标注改成含 `run/aclose/stats` 的协议」——**行不通**：
   `tests/contracts/test_core_contracts.py::test_ai_resilience_shape` 断言所有实现满足 `AiResilience`，
   加方法会让 `UnimplementedAiResilience` 不再满足（我第一版就是这么改的，跑全量时被这条契约测试抓住）。
   改为新增 `AiResilienceSnapshot`（`stats` + `aclose`），`AiResilience` 保持 run-only。

### 5.2 修 IE-01 时发现的连带缺陷（已一并修）

重试**再次**失败时，`_rollback_evaluation` 会用同一个 `request_id` 再 `add()` 一行 → 撞 `uq_interview_answers_session_request`，
把供应商错误掩盖成 `IntegrityError`。已改为按 `resume_of` 分支、复用同一行并刷新失败原因；新增用例 `test_a_retry_that_fails_again_still_keeps_one_row`。

### 5.3 本轮引入并已修复的两条回归（诚实记录）

1. **契约回归**：第一版给 `AiResilience` 协议加了 `stats/aclose` → `test_ai_resilience_shape` 红。已按 §5.1-3 改法修正。
2. **引证回归**：本轮改动移动了被审计引用的行号 → `tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`（逐字级，D22 的已知代价）变红。
   处置：按「窗口只扩不缩」重锚 `docs/audit/units/*.json`（详见 §6 的诚实清单）。

## 6. 复跑命令（逐条）

```bash
# 1 N1
cd apps/api && uv run pytest tests/test_scene_routing.py tests/test_chat_api.py -q
# 2 IE-01
uv run pytest tests/interview_engine/test_answer_service.py tests/test_interview_answers_api.py -q
# 3 chat-02
uv run pytest tests/test_chat_service.py tests/test_chat_api.py tests/test_conversation_store.py -q
# 4 identity_jobs-01
uv run pytest tests/test_settings.py tests/test_redis_client.py -q
# 5 so-03
uv run pytest tests/test_resilience_api.py -q
# 6 db-03（守卫 + 变异证明）
uv run pytest tests/test_migrations.py -q
bash scripts/verify_mutation.sh --test 'bash /tmp/p8_vocab_test.sh' \
  --file apps/api/src/better_resume/interview_engine/session_fsm.py \
  --find 'ABANDONED = "abandoned"' --replace 'ABANDONED = "abandoned_v2"'
# 7 media-01
uv run pytest tests/media tests/test_media_ws.py -q
# 8 web-04
cd '/root/better resume' && pnpm -C apps/web test --run
```

> 同上：所有 pytest 命令都需要先 `export BR_DATABASE_URL=… BR_REDIS_URL=…`（不导出会静默 skip 136 条，而不是失败）。
