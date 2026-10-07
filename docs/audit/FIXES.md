# 审计问题修复台账（FIXES）

> 配套 `docs/audit/MODULE-AUDIT.html`（122 条问题清单）。本文件只记录**已经开始动手**的条目：
> 改了什么、为什么这么改、怎么验证、还剩什么没验证。审计 JSON 里对应的 issue 会带 `fix_record` 字段，
> HTML 里显示为绿框「已修复 / 修复中」。
>
> 记录原则（沿用仓库纪律）：证据优先于叙述；未验证项必须写出来；不自行宣布完成。

## 状态总览

| 审计编号 | 严重度 | 一句话 | 状态 | 改动文件 |
| --- | --- | --- | --- | --- |
| ai-02 | 高 | token bucket 的补充算术在 Python 与 Lua 各写了一遍 | **已修复**（含一条已知边界） | redis_buckets.py、tests/ai_resilience/test_ratelimit_equivalence.py |
| conversation_chat-02 | 高 | 「取一条属于我的会话」没有 store 方法，用 list_for_user(limit=200) 线性找 | **已修复** | conversation/store.py、chat/service.py、tests/test_chat_service.py |
| IE-01 | 高 | 失败的答案行占用成功幂等键，同 request_id 重试分数永久拿不回 | **已修复**（语义 = 原地重评） | interview_engine/answer_service.py、answer_repo.py、tests/interview_engine/test_answer_service.py、tests/test_interview_answers_api.py |
| resume_parser_db-03 | 中 | 会话状态词表三份拷贝，alembic check 对 CHECK 文本完全盲 | **已修复** | interview_engine/orm.py、tests/test_migrations.py |
| settings_observability-03（so-03） | 高 | 分布式包装类缺 stats()，开关一开 /resilience/stats 必 500 | **已修复** | ai_resilience/protocols.py、distributed.py、main.py、tests/test_resilience_api.py |
| identity_jobs-01 | 高 | 哨兵「成对且可用」两份判据不等价，分隔符值静默退回单节点 | **已修复** | settings/config.py、redis_client.py、tests/test_settings.py |
| web-04 | 高 | 用回答内容相等去重，同一条回答出现两次时第二条被静默吞掉 | **已修复** | apps/web/src/chat/selectors.ts、selectors.test.ts |
| media-01 | 中 | assembler→事件映射在两个适配器里逐行重复，且没有一致性守卫 | **已修复**（抽取成一份 + 源码警报） | media/event_map.py、media/adapters/{xunfei_ast,scripted}.py、tests/media/test_event_map.py |
| （新发现，非审计条目）N1 | — | 测试污染：切场景的用例不还原共享绑定表 → 单跑 tests/test_chat_api.py 必 6 假红 | **已修复** | apps/api/tests/conftest.py、tests/test_scene_routing.py |

---

## ai-02 · token bucket 补充算术双写（Python ↔ Lua）

**来源**：`MODULE-AUDIT.html#ai-02`（ai_resilience 单元，高）
**原始证据**：`ai_resilience/ratelimit.py:77-85`（`TokenBucket.take`，Python 权威）与
`ai_resilience/redis_buckets.py:23-49`（`_TAKE_LUA`，Redis 侧镜像）；
`redis_buckets.py:1-14` 的 docstring 自称两者 "same arithmetic"。

### 为什么要修

同一份知识（令牌补充与扣减的算术）有两个手写副本，分别决定**共享配额**（Redis，多副本一份）与
**降级配额**（Redis 不可用时退到进程内桶，D19）的行为。docstring 声明二者等价，但没有任何测试强制——
任何一处改动（`retry_after` 口径、burst 语义、elapsed 取整/运算顺序）都会让两条路径悄悄分叉，而 CI 不会红。
这正是审计判据「重复的是知识，不是代码长相」命中的形态：两份实现长得不像，但必须永远保持一致。

### 方案选型（为什么不是"合并成一份实现"）

| 方案 | 结论 |
| --- | --- |
| A. 删掉 Lua，把算术收敛成 Python 一份 | **否决**。跨副本的 read-modify-write 必须原子；搬到 Python 侧要引入 WATCH/MULTI/重试循环或接受非原子读改写——行为变更，超出本次范围，且违反 P7/D19 已确认的语义。 |
| B. 让 Lua 成为唯一实现，进程内路径也走 Redis | **否决**。降级路径的全部意义就是 Redis 不可用时仍能限流（D19），它不能依赖 Redis。 |
| C. 源码级文本一致性测试（只钉 Lua 文本） | **降级采用**：单独用太弱（钉的是字符串不是算术），只作为第 3 条粗粒度警报。 |
| D. 用 fakeredis 执行 Lua 做真·等价契约 | **否决（环境不可达）**：fakeredis 执行 `EVAL` 需要 `lupa`，而 lupa 不在依赖树；CI 是 `uv sync --frozen`，测试写进去必红，加 skip 等于契约失效；加 lupa 属新增原生依赖，按依赖纪律需单独提案。 |
| **E（采用）** 把 Lua 算术收敛成一处可执行定义，再叠两条闭合断言 | **采用**。在 `redis_buckets.py` 里把 Lua 的算术照抄成一个**纯 Python 镜像函数**（运算顺序与 Lua 字面一致），于是"重复的算术"变成一处可执行、可单测的定义；再用等价断言 + 数值向量 + 源码警报把两份实现钉在一起。 |

### 关键环境事实（决定了方案选择）

- `fakeredis 2.38.0` 在依赖里，但**执行 Lua 需要 `lupa`**，而 `lupa` 不在 `uv.lock`。实测：
  `await FakeRedis(decode_responses=True).eval(_TAKE_LUA, ...)` → `redis.exceptions.ResponseError: unknown command 'eval'`。
  根因位置：`fakeredis/commands_mixins/__init__.py` 用 try/except 包住 `scripting_mixin`，缺 lupa 时 `server_supports_lua_scripts = False`。
- CI backend job 是 `uv sync --frozen`（`.github/workflows/ci.yml`），所以**依赖树里没有的东西 CI 也没有**。
- 本机 PyPI 可达（直连与 7897 代理均 HTTP 200），但"加一个原生依赖"按 AGENTS.md 依赖纪律要单独提案，本次不动。

### 改动

**A. apps/api/src/better_resume/ai_resilience/redis_buckets.py（+56 / -4）**

| 位置 | 改了什么 |
| --- | --- |
| L4-10 | 模块 docstring：删掉「keeps the *same* arithmetic」这句无人强制的声明，改成「脚本算术镜像进程内 TokenBucket；可执行定义是 take_lua_math；由 tests/ai_resilience/test_ratelimit_equivalence.py 钉住——改一侧必须改另一侧，否则测试红」。顺带把差异条目写准：脚本用 tostring 回字符串、由 take 转回 int/float（原文「numbers come back as integers」有歧义）。 |
| L27-33 | _TAKE_LUA 上方新增警告：这是 Redis 侧镜像；可执行定义在 take_lua_math；**运算顺序必须保持 elapsed / 1000 * rate，不得写成 elapsed * rate / 1000（两者舍入不同）**。 |
| L66-104 | 新增纯函数 take_lua_math(...)：把 Lua 的算术照抄成可执行 Python（空存 → cap/now、elapsed 负值钳 0、tokens + elapsed / 1000 * rate、> cap 封顶、>= 1 扣 1 返回 True/0.0/floor，否则 False/(1-tokens)/rate），返回脚本回复 + 它写回的状态 (allowed, retry_after, remaining, tokens_after, ts_after)。 |

**关键事实：_TAKE_LUA 的 Lua 文本逐字节未变**——脚本块 718 字符、sha256 552672b88a893730…，与 HEAD 版本完全一致（改的只有它上面的注释）。即本次是**纯增量的可测试化 + 注释纠偏，零行为变更**。

**B. apps/api/tests/ai_resilience/test_ratelimit_equivalence.py（新增，270 行，4 条用例 / 16 例）**

| 用例 | 钉住什么 |
| --- | --- |
| test_lua_mirror_matches_hand_computed_vectors（7 场景） | 镜像函数 vs 手算向量的绝对值 |
| test_token_bucket_and_lua_mirror_never_disagree（7 场景） | **取代 fakeredis 的等价断言**：同表驱动 TokenBucket（ManualClock）与镜像，比 allowed / remaining 精确、retry_after 1e-9 内、原始 tokens 按位 |
| test_lua_source_still_implements_the_same_formula | 源码级粗粒度警报：Lua 里关键式仍在，且 RedisBucketStore.take 跑的确实是 _TAKE_LUA |
| test_store_take_evals_the_lua_and_converts_its_string_reply | 字符串回复转 bool/float/int 不漏出去；eval 的 numkeys / ARGV 顺序（假 Redis 客户端，Redis 是允许 mock 的系统边界） |

场景表（7 条）：burst 耗尽、retry 数值分叉、精确补满边界、长空闲封顶、非整数 capacity 取整、极小 rate、**运算顺序敏感**（7ms @ 0.3/s：(7/1000)*0.3 = 0.0021 而 (7*0.3)/1000 = 0.0021000000000000003）。

诚实边界：测试文件头部与下方「未验证」都写明「Lua 在本环境无法执行」，以及 Lua tostring（%.14g）往返带来的 ~1e-14 尾数漂移未被断言。

### 验证

复核命令（可复跑）：

```bash
cd "/root/better resume/apps/api"
export BR_DATABASE_URL="postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume"
export BR_REDIS_URL="redis://127.0.0.1:6379/0"
uv run pytest tests/ai_resilience/ -q --junitxml=/tmp/after.xml     # 基线 85 → 101，0 failed / 0 skipped
uv run ruff format --check . && uv run ruff check                  # 250 files formatted；All checks passed
# Lead 的独立红/绿证明（旧的一次性脚本 verify_ai02_contract.sh 已删除，改成通用工具）：
bash scripts/verify_mutation.sh \
  --test "cd '/root/better resume/apps/api' && ./.venv/bin/python -m pytest tests/ai_resilience/test_ratelimit_equivalence.py -q" \
  --file apps/api/src/better_resume/ai_resilience/redis_buckets.py \
  --find "tokens = tokens + elapsed / 1000 * rate" --replace "tokens = tokens + elapsed * rate"
```

**证据 1 · 测试数字（Lead 独立复跑）**：tests/ai_resilience/ **85（改前）→ 101（改后），failures 0 / errors 0 / skipped 0**。

**证据 2 · Lead 的独立反向验证**（不是执行方自报；用 `scripts/verify_mutation.sh` 把 Lua 的补充式改成 elapsed * rate，该脚本会真断言「基线绿 → 变异红 → 恢复绿」并校验 sha256）：

```text
=== GREEN: contract test against the real implementation ===      (7 passed)
=== MUTATE: corrupt the Lua refill (elapsed/1000*rate -> elapsed*rate) ===
mutated
=== RED (expected): same test must now fail ===
FAILED tests/ai_resilience/test_ratelimit_equivalence.py::test_lua_source_still_implements_the_same_formula
=== RESTORED: implementation is back to green ===                 (7 passed)
```

**证据 3 · 执行方自报的第二次反向验证**（镜像改序 elapsed * rate / 1000，这条是等价断言的牙齿）：

```text
AssertionError: order_sensitive_refill step 1
assert 0.0021000000000000003 == 0.0021
FAILED ...::test_token_bucket_and_lua_mirror_never_disagree[order_sensitive_refill]
```

**证据 4 · Lua 文本未被改动**：脚本块 718 字符、sha256 552672b88a893730…，与 git show HEAD:…redis_buckets.py 中的逐字节一致 → 本次改动不可能改变线上行为。

**证据 5 · 全量后端（Lead 独立复跑）**：858 tests / 0 failures / 0 errors / 0 skipped（64.9s，junitxml 读数）。

### 与规格的偏差（Lead 已裁定：接受）

| 偏差 | 裁定 | 理由 |
| --- | --- | --- |
| take_lua_math 返回 **5 元组**（多 tokens_after / ts_after） | **接受** | 后两项是脚本 HSET 写回的状态。没有它们，场景表就得在测试里再抄一份状态更新——那等于引入第三份算术，正好违背本修复的初衷；对外三项语义不变。 |
| 等价用例增加 **tokens 按位比较** | **接受** | 运算顺序改动只差 1 ULP：allowed 不变、remaining 被 floor 吃掉、retry 在 1e-9 容差内——规格里的三项比较会**放过**这个 mutation。按位比较是这条断言唯一能红的原因。 |
| 增加第 4 条用例（字符串转换契约） | **接受** | C′ 方案下规格第 4 项原本会丢；假 Redis 客户端 mock 的是允许 mock 的系统边界，生产代码零改动。 |
| 场景表增加 order_sensitive_refill（7ms @ 0.3/s） | **接受** | 我原建议的 (1234ms, 0.3) 经实测两种顺序逐位相同、构造不出红；执行方自己扫出这一对，并用它证明了红。 |

### 未验证 / 已知边界

- **Lua 本身在本环境无法执行**：等价性是「镜像 ↔ TokenBucket（可执行、逐位）」＋「Lua 文本 ↔ 关键式（源码警报）」两层保证，**不是** Redis 端真实执行结果的机器验证。原因：fakeredis 执行 EVAL 需要 lupa，而 lupa 不在 uv.lock，CI 又是 uv sync --frozen。
- 因此本修复把风险从「无声分叉」降级为「必须同时改两处，且源码警报会提示」，但**没有消除「两份实现」这个事实**。彻底消除需要引 lupa（方案 D）或改为 Python 侧原子 RMW（方案 A），两者都需单独提案。
- 真实 Redis 路径的 Lua tostring（%.14g）往返会带来 ~1e-14 量级相对漂移，本次未加断言（原规格也未要求消除）。
- 键 TTL 与 max_identities 懒淘汰仍是两种过期策略，未做等价断言（按规格「别和等价性混在一起」）。

### 全量回归

`uv run pytest -q --junitxml=/tmp/ai02-full.xml`（apps/api，带 BR_DATABASE_URL / BR_REDIS_URL）：

```text
tests=858 failures=0 errors=0 skipped=0 time=64.885s
```

改动前基线（同一命令口径下的 ai_resilience 子集）：85 tests；改动后 101 tests。


---

## 环境改进（retro 2026-10-06）

不是审计条目，而是这次审计/修复过程中暴露的**验证工具自身**的问题。记在这里是为了让后人知道这些脚本为什么长这样。

| # | 问题（当时的真实症状） | 处置 | 证据 |
| --- | --- | --- | --- |
| R1 | `scripts/verify_ai02_contract.sh`（我写的证明脚本）恒退 0：`\| tail -3` 吞退出码、末行 `\|\| true`、先印「RED (expected)」再执行——**红没红都报成功** | 删掉，改成通用工具 `scripts/verify_mutation.sh`：断言基线绿 / 变异红 / 恢复绿，恢复后校验 sha256，三种失败各有独立退出码（1/2） | `bash scripts/verify_mutation.sh --test "true" --file … --find 存在锚点` → exit 1「the test stayed green on the mutation」；锚点缺失 → exit 2；端到端 PASS 输出见上 |
| R2 | `verify.sh` 的 scripts 层**从没在 CI 里跑过**（自测存在、调用缺失），新 shell 脚本完全没有语法闸门 | `.github/workflows/ci.yml` 增加 `bash scripts/verify.sh --layer scripts` 步骤；scripts 层补 shell 语法循环 + 脚本语法检查 + 引证门禁 | 见下方 R3/R4 的实测 |
| R3 | **我自己第一版修法就是坏的**：`bash -n scripts/*.sh` 只检查第一个文件（`bash -n a.sh b.sh` 把 b.sh 当位置参数） | 改成逐文件循环；`.githooks/pre-commit` 同样逐文件 | 用一个排在**最后**的坏脚本实测：glob 版 exit 0（漏检），循环版 exit 1（抓到） |
| R4 | 同类第二次：脚本语法扫描用 `glob.glob('../scripts/*.py')`，而从 `apps/api` 看 `../scripts` 是 `apps/scripts`——**仓库根脚本从未被检查** | 抽成 `scripts/check_scripts.py`（按 `__file__` 定位两个脚本目录），并把 SyntaxWarning 升为错误 | 首次运行即抓到两处**既有**的无效转义告警（`fault_probe.py:6`、`real_model_smoke.py:77`），已修；现在 21 个脚本全绿 |
| R5 | 审计引证核对器对「15 条引证未被证据佐证」只报告、仍退 0；且只认一种注释形状（`path:line  text`），另一种（`1: text`）永远匹配失败 | 加 `--strict`（partial 即失败）与 `--units DIR`；正则接受两种形状；只写 122 条中的 15 条被修准（**未删 where、未降 severity**，全部是补原文或统一形状） | `python3 scripts/verify_audit_evidence.py --strict` → `verifiable: 122 partial: 0 unverifiable: 0`，exit 0 |
| R6 | 子智能体里 `uv` 默认写工作区外缓存 → 权限拒绝，`test_real_layer` 两例**假红** | `AGENTS.md` §环境准备 记 `UV_CACHE_DIR`（子智能体也照此） | 本会话后续所有 `uv` 调用均先导出该变量 |
| R7 | 团队席位上限 8，**provisioning 失败的成员仍占名额且名字被永久占用**（retry 报 `TEAM_MEMBER_NAME_TAKEN` / `TEAM_MEMBER_LIMIT`），导致 Spec 轴评审只能改用 fork 子代理 | **会话内无法修复**：本会话 38 个工具里没有任何成员移除/退场 API（只有 `spawn_teammate` / `list_agents` / `interrupt_agent` / `wait_agent` / `team_task_*`），`interrupt_agent` 对 failed 成员直接报 `active teammate not found`。对策：失败后**不要同名重试**（名字永久占用），改用 `subagent_fork`（不计入团队席位）；要把团队当资源用，就得接受两个 failed 席位是永久损失 | `review-standards` / `review-spec` 停在 `failed`；`interrupt_agent` → not found；本会话非 lead 成员恒为 8（=上限），此后任何 `spawn_teammate` 都会撞限；11 个共享任务全部 completed，failed 成员名下无任何任务或产物 |

**这次 retro 的落点**：`AGENTS.md`（UV_CACHE_DIR、变异证明用法、`docs/audit/` 与工具清单、harness 两条事实）、
`CODING_STANDARDS.md`（「声称验证必须真判定」列为判断项）、`.githooks/pre-commit`（可选提交前检查）、
`scripts/verify.sh` + `.github/workflows/ci.yml`（scripts 层真正跑起来）。

**复跑**：`bash scripts/verify.sh --layer scripts`（4 条命令；本次输出 `ALL PASS`，含 66 passed、21 脚本语法、122/0/0 引证）。

---

## 记录模板

```markdown
## <审计编号> · <一句话>

**来源**：`MODULE-AUDIT.html#<编号>`（<模块> 单元，<严重度>）
**原始证据**：<文件:行号 与原文摘录>

### 为什么要修
<调用者/维护者付出的代价；引用具体判据>

### 方案选型
| 方案 | 结论 |
| --- | --- |
| A ... | 采用/否决 + 理由 |

### 改动
<文件 + 行号 + 改了什么>

### 验证
<可复跑命令 + 原始输出片段 + 数字>

### 未验证 / 已知边界
<诚实清单>
```| conversation_chat-02 | 高 | 「取一条属于我的会话」没有 store 方法，用 list_for_user(limit=200) 线性找 | **已修复** | conversation/store.py、chat/service.py、tests/test_chat_service.py |
| IE-01 | 高 | 失败的答案行占用成功幂等键，同 request_id 重试分数永久拿不回 | **已修复**（语义 = 原地重评） | interview_engine/answer_service.py、answer_repo.py、tests/interview_engine/test_answer_service.py、tests/test_interview_answers_api.py |
| resume_parser_db-03 | 中 | 会话状态词表三份拷贝，alembic check 对 CHECK 文本完全盲 | **已修复** | interview_engine/orm.py、tests/test_migrations.py |
| settings_observability-03（so-03） | 高 | 分布式包装类缺 stats()，开关一开 /resilience/stats 必 500 | **已修复** | ai_resilience/protocols.py、distributed.py、main.py、tests/test_resilience_api.py |
| identity_jobs-01 | 高 | 哨兵「成对且可用」两份判据不等价，分隔符值静默退回单节点 | **已修复** | settings/config.py、redis_client.py、tests/test_settings.py |
| web-04 | 高 | 用回答内容相等去重，同一条回答出现两次时第二条被静默吞掉 | **已修复** | apps/web/src/chat/selectors.ts、selectors.test.ts |
| media-01 | 中 | assembler→事件映射在两个适配器里逐行重复，且没有一致性守卫 | **已修复**（抽取成一份 + 源码警报） | media/event_map.py、media/adapters/{xunfei_ast,scripted}.py、tests/media/test_event_map.py |
| （新发现，非审计条目）N1 | — | 测试污染：切场景的用例不还原共享绑定表 → 单跑 tests/test_chat_api.py 必 6 假红 | **已修复** | apps/api/tests/conftest.py、tests/test_scene_routing.py |

---

---

## conversation_chat-02 · 按 id 取自己的会话（不再翻用户列表）

**来源**：`MODULE-AUDIT.html#conversation_chat-02`（conversation_chat 单元，高）。**实测证据**见 `docs/tickets/p8-audit-hardening/README.md` §1。

### 为什么要修

用户会话数超过 200 时，`ChatService._load` 先 `require_owner` 通过、再用 `list_for_user(limit=200)` 翻页线性找目标 —— 目标排在第 201 位就找不到，客户端拿到 **HTTP 200 + SSE error 帧**（审计原文写的 404 不成立：异常在 SSE 生成器里被吞）。

### 改了什么

store 新增 `get_owned(session, user_id)`：一次查询同时完成归属校验与取行；`_load` 直接委托它，删掉翻页查找。归属失败仍一律 `ConversationNotFoundError`（对外 404 语义不变）。

### 怎么验证

修前红：201 条会话时新用例抛 `ConversationNotFoundError`；修后 `tests/test_chat_service.py + test_chat_api.py + test_conversation_store.py` = **27 passed / 0 failed**。

### 未验证 / 边界

只覆盖 chat 会话；`list_for_user` 仍不按 `kind` 过滤（当前无 interview 会话写入该表）。审计提到的「未来 interview 会话会挤掉 chat」属潜在项，未处理。

---

## IE-01 · 失败的一次作答不该吃掉幂等键

**来源**：`MODULE-AUDIT.html#IE-01`（interview_engine 单元，高）。

### 为什么要修

评分失败时 `_rollback_evaluation` 用**同一个** `request_id` 写一行 `score=NULL` 的失败记录；幂等闸门只查「这行在不在」，于是按契约重发同一 `request_id` 的客户端拿到 `201 + replayed=true + score=None`，而唯一约束保证再也写不进第二行 —— 该题分数**永久拿不回**（实测：换新 id 才拿到 84.0）。

### 改了什么

按用户拍板的 **(b) 原地重评**：命中失败行（`error_message` 非空）时不再 replay，而是走完整评分并**原地覆写该行**（`AnswerRepository.overwrite`）；命中成功行仍 replay。**连带缺陷**：重试再次失败时原实现会用同一个 key 再 `add()` 一行 → 撞 `uq_interview_answers_session_request`、把供应商错误掩盖成 `IntegrityError`；现按 `resume_of` 分支复用同一行并刷新失败原因。

### 怎么验证

修前红：服务层 `replayed=True`；HTTP 面同 id 重试 = 201 + `score=None`。修后 `tests/interview_engine/test_answer_service.py + tests/test_interview_answers_api.py` = **20 passed / 0 failed**，含三条新用例（同 id 重试拿分、重试再失败仍一行、HTTP 同 id 重试拿分）。

### 未验证 / 边界

语义变更：幂等键现在「可重入直到成功」。第一方前端 `useInterviewRoom.ts` 每次点击都换新 id，所以 UI 行为不变；受影响的是**按契约重发同 id 的消费者**（丢包重发、脚本、第三方）。

---

## resume_parser_db-03 · 状态词表只留一份真相 + 一条会变红的守卫

**来源**：`MODULE-AUDIT.html#resume_parser_db-03`（resume_parser_db 单元，中）。

### 为什么要修

会话状态词表有三份手写拷贝（`SessionStatus` 枚举 / ORM `CheckConstraint` / 迁移里的 CHECK 文本），而 `alembic check` **看不见 CHECK 文本**：实测在内存里改写甚至删除 ORM 的约束 → `compare_metadata` 仍报 **0 op**（对照：多加一列 → 1 op）。改一处漂两处，且只在第一次写新状态时才炸成 `CheckViolationError`。

### 改了什么

ORM 侧改为由枚举派生（`_STATUS_CHECK = "status IN (...)"` 从 `SessionStatus` 生成），删掉一份字面量；迁移文本不动（历史不可改）。

### 怎么验证

新增 `tests/test_migrations.py::test_the_status_vocabulary_agrees_across_code_the_orm_and_the_database`：从 Postgres 读回 `pg_get_constraintdef`，比对「枚举 ↔ ORM 约束 ↔ 数据库」三处的字面量集合。**变异证明**：`bash scripts/verify_mutation.sh` 把枚举里 `ABANDONED` 的值改掉 → 该用例变红；恢复后变绿，且 sha256 与 HEAD 一致（基线绿 → 变异红 → 恢复绿）。

### 未验证 / 边界

只钉 `ck_interview_sessions_status`；同模式的 `conversations/messages` 两条约束（审计同一单元里提到）未加断言。迁移文本仍是第三份拷贝 —— 现在它漂了会被守卫抓住，但**不会**被自动修正。

---

## settings_observability-03 · 包装类必须替它所包的链路作答

**来源**：`MODULE-AUDIT.html#settings_observability-03`（settings_observability 单元，高；unit JSON 里 id 为 `so-03`）。

### 为什么要修

打开分布式单飞（`BR_RESILIENCE__DISTRIBUTED=true`）后，`app.state.ai_resilience` 被换成 `DistributedAiResilience`，它只有 `run/aclose`、没有 `stats()`；而 `main.py` 把该变量标注成 `object`，类型信息被抹掉，于是 `GET /api/v1/resilience/stats` 对已登录调用者 **100% 500**（实测真 app + 真 PG/Redis + 真登录）。

### 改了什么

`DistributedAiResilience.stats()` 委托 `self._inner.stats()`；新增 `AiResilienceSnapshot` 协议（`stats` + `aclose`）并把装配点标注改成它。**没有**给 `AiResilience`（run-only 契约）加方法 —— 第一版那样改会让 `UnimplementedAiResilience` 不再满足 `tests/contracts/test_core_contracts.py::test_ai_resilience_shape`，被全量跑抓红。

### 怎么验证

修前红：`AttributeError: 'DistributedAiResilience' object has no attribute 'stats'`（pytest 1 failed）。修后 `tests/test_resilience_api.py + tests/ai_resilience + tests/test_distributed_flight.py + tests/test_healthz.py` = **117 passed / 0 failed**，含新用例（distributed=true 时 /stats 必须 200）。

### 未验证 / 边界

后端**没有** mypy/pyright 门禁，协议标注只是文档级约束：下次再包一层忘了 `stats` 不会在 CI 变红，真正拦住它的是那条新用例。默认部署（开关关）本来就 200，故这条对现网无影响。

---

## identity_jobs-01 · 哨兵判据收敛成一份

**来源**：`MODULE-AUDIT.html#identity_jobs-01`（identity_jobs 单元，高）。

### 为什么要修

`BR_REDIS_SENTINELS` 的「成对且可用」有两份判据：`Settings` 校验只看「有没有字符」(`bool(strip())`)，`RedisTopology.from_settings` 则过滤空项后再判空。于是只含分隔符的值（`","` / `" , "`）**能过启动校验**，运行时静默退回单节点客户端（`uses_sentinel=False`、普通 `ConnectionPool`）—— 多副本下主挂了不切换，**无异常、无日志**。

### 改了什么

新增 `settings.config.parse_sentinel_addresses` 作为「什么算配了哨兵」的唯一判据（settings 拥有、redis_client 复用）；校验里补一条：原始值非空但解析不出地址 → 启动即拒并点名变量。**地址语法**仍归 `redis_client._sentinel_address`（它对 `x:abc` 本来就抛，实测确认「响的」）。

### 怎么验证

修前红：三个分隔符参数化用例全部 `DID NOT RAISE ValidationError`。修后 `tests/test_settings.py + test_redis_client.py + test_distributed_flight.py + test_identity.py` = **39 passed / 0 failed**；另加一条「validator 与 topology 读法一致」的契约用例。

### 未验证 / 边界

只覆盖「算不算配了」这一层；语法层未合并（见上）。半配置（只给一半）与非法地址在改动前后都是响的，行为未变。

---

## web-04 · 回答的身份锚在它那一轮，而不是它的文本

**来源**：`MODULE-AUDIT.html#web-04`（web 单元，高）。

### 为什么要修

`mergeHistory` 用「assistant 回答的**文本内容**是否与历史里某条完全相同」判断草稿是否已落库。连续两次回答内容相同（模板化上游、连点两次「你好」）时，第二条在 refetch 落地前就被当成「已回放」静默吞掉 —— 用户看着刚出现的回答消失；refetch 失败则**永久不回**（调查员在真 `ChatPage` 上复现）。

### 改了什么

去重改为**按回答所属那一轮的 `client_message_id`**：先算出「历史里已被回答的用户轮」（该轮之后的第一条 assistant 行），本地草稿只在它自己那一轮**尚未被回答**时才保留；内容比较只留作「草稿前面没有用户轮」时的兜底。

### 怎么验证

修前红：`Tests 1 failed | 5 passed`（新用例「第二条相同回答必须留下」）。修后前端 **177 passed**（24 文件）、`eslint` 与 `tsc --noEmit` 干净。

### 未验证 / 边界

**没有**按提案写的「`ChatMessage` 带服务端 id」：SSE 的 `done` 帧只带 `finish_reason`，草稿拿不到服务端 `seq`，那要改传输协议（超出本轮范围，已记进 ACCEPTANCE §5.1）。

---

## media-01 · 映射规则只留一份 + 源码警报

**来源**：`MODULE-AUDIT.html#media-01`（media 单元，中）。

### 为什么要修

assembler 快照 → `TranscriptEvent` 的映射在 `xunfei_ast._emit_update` 与 `scripted._apply` 里逐行重复（含各自一份 `_committed_seen` 记忆），而 `scripted` 是本地/CI 的默认通道；两份当前等价（差分实测一致），但**没有任何测试要求它们一致** —— 只改一份，默认通道的多句切片就与供应商通道分叉，套件仍绿。

### 改了什么

把规则与它的记忆抽成 `media/event_map.py` 的 `TranscriptEventMapper.events()`，两个适配器只负责喂包（各自删掉 `_committed_seen`）。

### 怎么验证

新增 `tests/media/test_event_map.py`：两句四个包 → `[replace, archive, replace, archive]`（此前无人钉住多句切片）、重复 final 包不重复 archive、以及「适配器里不许再出现 `update.committed[`」的源码警报。`tests/media + test_media_ws.py + test_media_tts_api.py` = **79 passed / 0 failed**。

### 未验证 / 边界

`paraformer_rt.py` 是同一规则的第三份实现（按供应商 `sentence_end` 驱动、不经 assembler），**未动**（来源不同，属合理实现）。等价证明是结构性的（只有一份 + 警报），不是两适配器逐帧对拍。

---

## N1 · 测试污染：共享的场景绑定表要还原（非审计条目，本轮实测发现）

**来源**：本机实测（`docs/tickets/p8-audit-hardening/README.md` §1 的 N1 段有完整因果链原始输出）。

### 为什么要修

`tests/test_scene_routing.py` 用真 `PUT /api/v1/scenes` 把 chat 场景切到 `xingyun:flow-chat`，前 4 处手动还原、**第 5 处（文件最后一个用例）漏了** —— 绑定表在进程外、被整个 run 共享，于是任何**只跑子集**的人（`pytest tests/test_chat_api.py`、`-k chat`）都会看到 **6 条假红**，理由全是「缺 XINGCHEN_API_KEY」，与他的改动无关。全量跑为什么一直绿：store 测试的 fixture 恰好在那之前把整表重置。

### 改了什么

`tests/conftest.py` 新增快照/还原 fixture `restore_scene_bindings`（记录五行、只在与快照不同时写回），`test_scene_routing.py` 用模块级 `pytest.mark.usefixtures` 全量套用；再加一条**同文件内、顺序确定**的回归用例（断言「前序用例切换过的场景回到默认」）。

### 怎么验证

修前红：`pytest tests/test_scene_routing.py tests/test_chat_api.py` = **14 tests / 7 failed**（新用例 `AssertionError: chat was left on xingyun:flow-chat` + chat_api 六条）。修后同命令 **14 / 0**；单文件 6 / 0。

### 未验证 / 边界

fixture 只加在**已知污染者**上（+ conftest 供复用），**没有**做全局 autouse —— 那会让 865 条用例全部强依赖数据库，破坏「无 DB 时其余用例照跑」。其它文件若将来切换场景，需要自己套用这个 fixture。
