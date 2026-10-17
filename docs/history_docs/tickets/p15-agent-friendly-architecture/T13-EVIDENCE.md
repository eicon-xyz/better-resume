# T13 证据：缓存对象自带写路径失效语义

## 意图复述

- 我理解这票解决什么：P10 的三种复发形态（读缓存忘写路径失效、进程内配置缓存跨副本漂移）现在都靠「调用方记得调 invalidate」——热层的 `_invalidate_hot` 在 HTTP 端点里、场景绑定的 `resolver.invalidate` 也在 PUT 端点里；票要把「写后读一致」变成缓存对象自己的不变量，TTL 只做兜底。
- 我怎么做，到文件粒度：`llm_gateway/resolver.py` 增加写路径 API（绑定与本地失效同一处）、`http/scenes.py` 改为走它；`interview_engine` 的出题/答题/finish 三个写服务各接一个可选的热层失效钩子，`http/interview.py` 删掉 `_invalidate_hot` 这个调用方失效；用例写在 `tests/interview_engine/test_restore_report.py` 与 `tests/llm_gateway/test_scene_resolver.py`。
- 我不做什么：不改 HTTP/DB 面（路由、响应模型、迁移都不动）、不引依赖、不 commit/push/开 PR；不动工作区里 p14 在飞的未提交改动与 docs（本票证据文件除外）。

## 红-绿（先按票演示红）

红用的坏输入 = 实现落地前的工作区（2026-10-17 12:39，DB/Redis 已按 AGENTS.md 导出）：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t13-red.xml
uv run pytest -q tests/interview_engine/test_restore_report.py::test_every_write_path_drops_the_warm_hot_view tests/llm_gateway/test_scene_resolver.py::test_a_binding_write_through_the_resolver_is_read_back_immediately --junitxml=/tmp/t13-red.xml
```

原始输出（节选，逐字）：

```text
>       assert after_generate.source == "derived", "出题写路径没有失效热层"
E       AssertionError: 出题写路径没有失效热层
E       assert 'hot' == 'derived'
E         - derived
E         + hot
>       await resolver.bind(LlmScene.CHAT, AdapterKind.OPENAI_COMPAT, "deepseek-v4-pro")
E       AttributeError: 'SceneResolver' object has no attribute 'bind'
FAILED tests/interview_engine/test_restore_report.py::test_every_write_path_drops_the_warm_hot_view
FAILED tests/llm_gateway/test_scene_resolver.py::test_a_binding_write_through_the_resolver_is_read_back_immediately
=== junit ===
RED   tests.interview_engine.test_restore_report::test_every_write_path_drops_the_warm_hot_view
   AssertionError: 出题写路径没有失效热层
RED   tests.llm_gateway.test_scene_resolver::test_a_binding_write_through_the_resolver_is_read_back_immediately
   AttributeError: 'SceneResolver' object has no attribute 'bind'
```

两条红各自钉住票面点名的形态：

- 热层：写路径（出题）提交后，`restore` 仍命中写前的热键，返回 `source="hot"` 的过期视图——断言 `'hot' == 'derived'` 就是「写后读到过期视图」。
- 场景绑定：旧实现里写路径是 HTTP 端点里的 `SceneBindingStore.upsert` + `resolver.invalidate`（`http/scenes.py`），缓存对象本身没有写入口，所以用例在旧实现上以 `AttributeError` 红——它证明「失效语义不在对象上」。

红版用例与绿版只差两处构造：热层用例把 `hot_state=memory` 传给三个写服务（旧实现没有这个入参），场景用例把起始绑定点成已知默认值并在 `finally` 里还原；**断言行逐字未改**。红版输出是上面那次运行的原始输出，没有重跑补录。

## 验收命令与原始输出

### 1. 改后：两个用例转绿

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t13-targeted.xml
uv run pytest -v tests/interview_engine/test_restore_report.py::test_every_write_path_drops_the_warm_hot_view tests/llm_gateway/test_scene_resolver.py::test_a_binding_write_through_the_resolver_is_read_back_immediately --junitxml=/tmp/t13-targeted.xml
python3 - <<'PY'
import xml.etree.ElementTree as ET
root=ET.parse('/tmp/t13-targeted.xml').getroot()
suites=[root] if root.tag=='testsuite' else list(root)
print({k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')})
PY
```

```text
======================== 2 passed, 2 warnings in 0.86s =========================
{'tests': 2, 'failures': 0, 'errors': 0, 'skipped': 0}
```

### 2. 相关面定向集（缓存/恢复/答题/出题/报告/路由）

```bash
cd '/root/better resume/apps/api'
# 同上四个 env
uv run pytest -q tests/interview_engine/test_restore_report.py tests/llm_gateway/test_scene_resolver.py \
  tests/llm_gateway/test_scene_binding_propagation.py tests/test_hot_state.py tests/test_scene_routing.py \
  --junitxml=/tmp/t13-green2.xml
```

```text
{'tests': 39, 'failures': 0, 'errors': 0, 'skipped': 0}
```

### 3. 改后：缓存对象 API 含失效语义（写路径触发失效）

- 热层：`interview_engine/hot_state.py` 提供 `invalidate_hot_state(hot_state, *, user_id, session_id)`；三个写服务各自在**自己提交之后**调用它——`AnswerService.submit`（`try/finally`，失败路径同样失效：首答会先提交 `IN_PROGRESS`）、`QuestionService._persist`、`ReportService.finish/freeze`。`http/interview.py` 里的 `_invalidate_hot` 助手与 4 处调用点整体删除，端点上不再有失效语句。
- 场景绑定：`SceneResolver.bind(scene, adapter, target_ref)` 一次完成「落库 + 撤本地缓存」，`http/scenes.py` 的 PUT 只调 `resolver.bind(...)`，不再碰 `SceneBindingStore` / `resolver.invalidate`。其它副本仍由 5s TTL 收敛（票面口径：进程内配置缓存带 TTL 或写路径失效）。
- TTL 仍只是兜底：热层 `RedisHotState` 默认 600s、`InMemoryHotState` 由 put 传入；绑定缓存 `scene_binding_cache_seconds=5.0`，`test_default_ttl_is_short_enough_for_a_config_change_to_propagate` 保持绿。

### 4. 验收第 3 条：`_bindings|invalidate|cache` 逐条归属

```bash
cd '/root/better resume'
grep -rn "_bindings\|invalidate\|cache" apps/api/src/better_resume/llm_gateway apps/api/src/better_resume/interview_engine --include='*.py' | grep -v __pycache__ | wc -l
```

```text
58
```

逐条归属（按文件分组，58 行全部覆盖；`__pycache__` 的二进制命中不计）：

| 命中文件（行数） | 归属 |
| --- | --- |
| `llm_gateway/registry.py`（12） | `ModelRegistry` 的 30s TTL 模型表缓存。源表 `ai_models` 在应用内没有写路径（只由迁移 seed），所以 TTL 是它唯一的界；`invalidate()` 只有测试调用，本票未动。 |
| `llm_gateway/resolver.py`（20） | 场景绑定缓存本体：`_bindings`（缓存字典）、`invalidate()`（撤键，`bind()` 与用例调用）、`_cache_ttl` / `cached_at`（TTL 兜底）、`loads`（读库计数，断言用）。`bind()` 是本票新增的写路径。 |
| `llm_gateway/binding_orm.py`（1） | 表名 `llm_scene_bindings` 含 "bindings"，与缓存无关。 |
| `interview_engine/hot_state.py`（10） | 热层缓存：`HotStateStore` 协议（含 `invalidate`）、`InMemoryHotState` / `RedisHotState` 两实现（Redis 的失效失败只告警，不让缓存拖垮请求）、新增的 `invalidate_hot_state` 写路径助手。 |
| `interview_engine/restore_service.py`（4） | 热层的读侧：`get` 命中即返回、miss 时派生并 `put`；`"hot"/"derived"` 的 source 标记。本票未动。 |
| `interview_engine/answer_service.py`（2） | 写路径：import + `submit` 的 `finally` 失效。 |
| `interview_engine/question_service.py`（3） | 写路径：import、`_persist` 提交后失效；另一行是 `build_generation_key` 文档里的 "cached batch"（单飞回放，不是本票的读缓存）。 |
| `interview_engine/report_service.py`（3） | 写路径：import + `finish` / `freeze` 提交后失效。 |
| `interview_engine/corpus/matching.py:30`、`corpus/questions.json`（9） | 题库语料里的 "缓存/cache" 词条（Redis、HTTP Cache-Control、BuildKit cache mount 等题目），与代码缓存无关。 |

### 5. 验收第 4 条：后端全量 pytest

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t13.xml
uv run pytest -q --junitxml=/tmp/t13.xml
```

```text
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
=== junit ===
{'tests': 1009, 'failures': 1, 'errors': 0, 'skipped': 0}
BAD tests.test_verify_script test_every_audit_citation_is_corroborated_by_its_evidence | AssertionError: d_for
```

**这一条不是全绿**：1009 个用例里 1 个红，红的不是本票的行为面，而是 `scripts/verify_audit_evidence.py --strict` 的引证门禁（`docs/audit/units/*.json` 里的 `文件:行号` 复核）。逐条见「未验证项」第 1 条。

口径说明：12:45 那次全量曾出现大量 `DeadlockDetected` / `relation "interview_sessions" does not exist`，原因是另一个子代理（T14）同时在同一个测试库上跑全量（`/tmp/t14-b.xml`，12:43:19 起）。上面的读数是等那一轮结束、确认无并发 pytest 进程后重跑的干净口径。

### 6. 红线自查

```bash
cd '/root/better resume'
git status --porcelain -- apps/api/pyproject.toml apps/api/uv.lock apps/api/migrations compose.yaml | wc -l
```

```text
0
```

无新依赖、无迁移、无 compose 改动、路由与响应模型未动；`ruff format` + `ruff check src tests` 全过（`All checks passed!`）。

两个与本票相关的门禁自查（都在证据写完后跑）：

```bash
cd '/root/better resume'
bash scripts/verify_docs_hygiene.sh; echo "hygiene exit=$?"
bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/T13-EVIDENCE.md; echo "citations exit=$?"
```

```text
扫描 508 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
hygiene exit=0
引证 3（直配 0，短名兜底 3）解析成功 3 失败 0
citations exit=0
```

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 热层失效落在「写服务自己提交之后」，而不是缓存对象内的 mutate/写穿 | `RestoreView` 从 `interview_sessions`/`interview_questions`/`interview_answers`/`interview_flow_state` 四张表派生，缓存对象不认识这些写入；写路径的所有者（`AnswerService`/`QuestionService`/`ReportService`）是唯一拿得到 `user_id`（热键含用户维度）且知道「事务何时算提交」的地方。失效语句因此从 HTTP 端点搬到写路径内部，端点上零失效代码 | 没做 Redis pub/sub 或版本号广播：跨副本仍靠 600s TTL 兜底。票面口径只要求「进程内配置缓存带 TTL 或写路径失效」，做广播要新增频道/版本表，超出唯一写入路径的收益 |
| 新增模块级助手 `invalidate_hot_state(hot_state, *, user_id, session_id)`，而不是三处各写 `if self._hot_state is not None` | 三份 `None` 判断是三份会各自演化的副本；`HotStateStore` 是 Protocol，不能挂默认实现 | 没给 `HotStateStore` 加基类，也没把 `hot_state` 设成必填（worker 构造 `ReportService` 时不需要它） |
| 场景绑定用 `SceneResolver.bind()` 承载写路径，PUT 端点不再自己开 session + `invalidate` | 票面点名的正是「失效逻辑留在调用方」；把写入口收到缓存对象上，调用方没有可忘记的步骤。其它副本继续由 `scene_binding_cache_seconds=5.0` 收敛 | 没删 `resolver.invalidate()`：它现在是缓存对象自己的 API（`bind` 内部与用例调用），删掉会让「撤本地缓存」变成不可测的隐式行为 |
| `AnswerService` 用 `try/finally` 失效（失败路径也失效），`QuestionService` 只在成功提交后失效 | 首答会先把会话推进 `IN_PROGRESS` 并提交，之后评分失败走回滚也不会退回原状态——失败路径同样改写了派生视图，必须失效；出题失败时 `_rollback_to_draft` 把会话还原成调用前状态（删掉半写的问题、状态回 `DRAFT`），派生视图不变，不必失效 | 没给 `QuestionService.generate` 的整体失败路径加失效；没动 `_rollback_to_draft` 的语义 |
| 用例把「写前热键」用 `InMemoryHotState.put(...)` 预置，而不是先 `restore` 再出题 | 先 `restore` 一个无题会话会在读路径里派生并写 `interview_flow_state`，随后出题的 `initialize` 插入同一主键直接 `IntegrityError`（见未验证项第 3 条）。预置热键既避开这个无关缺陷，又更贴近真实形态——另一副本缓存了旧视图 | 没修「`restore` 在无题会话上写 flow 行、导致随后出题主键冲突」这个缺陷：它是读取路径写库的独立问题，超出本票红线（票面只允许改缓存对象、其调用点与用例） |
| 场景用例在 `finally` 里把 `chat` 绑定点回 `deepseek-flash` | `llm_scene_bindings` 是全量测试共享的表，AGENTS.md 要求用例自己还原跨进程共享状态；本文件原来的用例已经在互相依赖残留 | 没给整个 `test_scene_resolver.py` 换 fixture：那会动到并发子代理正在改的同一区域，超出本票需要 |

## 未验证项

1. **全量 pytest 不是全绿：1009 个用例里 1 个红**，红在引证门禁而不是行为面：

   ```bash
   cd '/root/better resume'
   apps/api/.venv/bin/python scripts/verify_audit_evidence.py --strict; echo "EXIT=$?"
   ```

   ```text
   FAIL  [http] http-06: 「哪些写操作要让 hot 缓存失效」是散在路由里的人际约定（同一行 ×4），没有任何地方强制
           apps/api/src/better_resume/http/interview.py:170-170: 0/5 evidence lines in window
           apps/api/src/better_resume/http/interview.py:284-284: 0/5 evidence lines in window
           apps/api/src/better_resume/http/interview.py:463-463: 0/5 evidence lines in window
           apps/api/src/better_resume/http/interview.py:463-463: 0/5 evidence lines in window
           apps/api/src/better_resume/http/interview.py:222-224: 0/5 evidence lines in window
   STRUCT http/http-13: apps/api/src/better_resume/http/interview.py:491-493 outside 1..490

   1 structural problem(s) in 10 unit(s)
   EXIT=1
   ```

   - `http-06` 的 5 条引证指的正是本票删掉的 4 处 `_invalidate_hot` 调用点与那个助手——门禁变红是「它描述的问题已消失」的直接证据，需要把该 unit 的 `fix_record` 写成已修。
   - `STRUCT http-13` 是本票在 `http/interview.py` 净删 9 行后，文件尾 `__all__` 从 491-499 移到 482-490，引证 491-493 越界。
   - 另有 14 条 `PART`：既有本票造成的行位移（`http/interview.py`、`answer_service.py` 等），也有并发子代理的「async 布尔→`ConfigStatus` 快照」票改 `llm_gateway/resolver.py` 造成的（`resolver.py:48-56 / 69-75 / 91-106 / 176-182`、`test_scene_resolver.py:100-109` 这些窗口都落在它重排的区段上）。
   - **没有动 `docs/audit/units/*.json` 去把它改绿**：本票红线写明「不动 p14 与 docs（本票证据文件除外）」，引证重锚属于 `docs/` 的写入。需要用户/父代理授权，或由引证重锚票统一处理；在此之前本票只能诚实记红。
2. **跨副本写后读一致没有专门演练**：热层走 Redis 键，失效天然跨副本（`test_hot_state` 已用真实 Redis 覆盖双实例读、失效与降级），但「实例 A 写、实例 B 立刻 restore」的组合只在单进程测试里验证过；绑定缓存的跨副本收敛只验证到 5s TTL（`test_scene_binding_propagation`），本票没有做主动广播。
3. **顺带发现、本票没改的缺陷**：`RestoreService.restore` 对无题会话会派生并写入 `interview_flow_state`（`total_questions=0`），随后 `QuestionService.generate` 的 `initialize` 插入同一主键 → `IntegrityError`（本票写红用例时实际撞到）。属读取路径写库与出题初始化的交互问题，不在本票范围。
4. **没跑**：`bash scripts/verify.sh --layer all`、`--layer coverage`、compose/真机演练、前端与契约三件套（本票没动 REST 模型、没动前端）。
5. **并发写口径**：`llm_gateway/resolver.py` 与 `tests/llm_gateway/test_scene_resolver.py` 同时被另一个子代理的 `ConfigStatus` 票修改。本票在这两个文件里的增量只有 `SceneResolver.bind()`（13 行，`git diff -U0` 计数）与 `test_a_binding_write_through_the_resolver_is_read_back_immediately`（20 行）；收工前复查两者都在，且 `ruff format` 后行号与上面贴出的读数一致。