# T17 证据包（审计引证重锚 + fix_record + scripts 层收口 + 隔离库权威全量）

## 意图复述

- 我做的是：T12/T13/T14 重构后，`docs/audit/units/*.json` 的引证锚点相对当前代码漂移（`verify_audit_evidence.py --strict` 由基线 122/0/0 掉成一批 partial/fail），逐条把 `where` 的行号/范围重锚回代码真实位置，让逐字级门禁恢复全绿；对被本轮重构真正修掉的 issue（如 http-06 引的 `_invalidate_hot` 已被 T13 删除）按 `docs/audit/CONTRACT.md` 记 `fix_record`。
- 边界：唯一写入面是 `docs/audit/units/` 的引证锚点与 `fix_record`，加本文件两段自述；不改审计结论、不动 issue 描述与代码、不动 p14 在飞改动、不 commit/push/开 PR。
- 验收：`--strict` 恢复全绿（partial 0 / problem 0）、层内 pytest 审计用例绿、`bash scripts/verify.sh --layer scripts` 退出 0、权威全量 pytest 在新鲜隔离库 `br_t17_verify` 上串行复跑绿。

## 验收读数

四条口径各自可复跑；每段都是命令的原始输出。

### 1 逐字级引证门禁：重锚前红 → 重锚后绿

把 HEAD 版 units 还原到临时目录（不碰工作区），对**同一份当前代码**跑**同一份判定代码**：

```bash
cd '/root/better resume'
rm -rf /tmp/t17_baseline_units && mkdir -p /tmp/t17_baseline_units
for f in $(git ls-files docs/audit/units); do git show HEAD:$f > /tmp/t17_baseline_units/$(basename $f); done
uv run --project apps/api python scripts/verify_audit_evidence.py --strict --units /tmp/t17_baseline_units; echo "EXIT=$?"
```

```text
PART  [http] http-01: db.get_session 是指定「全项目统一」的依赖，但全仓库没有调用者，真实写法是 29 处 request.app.state.se
        apps/api/src/better_resume/db/session.py:29-33: 5/8 evidence lines in window
        apps/api/src/better_resume/http/chat.py:81-81: 2/8 evidence lines in window
        apps/api/src/better_resume/http/interview.py:127-127: 2/8 evidence lines in window
        apps/api/src/better_resume/http/scenes.py:57-57: 0/8 evidence lines in window
PART  [http] http-03: 7 条业务路由里有 7 处把业务服务内联构造（QuestionService/AnswerService/ReportService ×4）
        apps/api/src/better_resume/http/interview.py:146-150: 2/11 evidence lines in window
        apps/api/src/better_resume/http/interview.py:257-261: 2/11 evidence lines in window
        apps/api/src/better_resume/http/interview.py:381-381: 2/11 evidence lines in window
        apps/api/src/better_resume/http/interview.py:432-432: 0/11 evidence lines in window
        apps/api/src/better_resume/http/interview.py:455-455: 2/11 evidence lines in window
        apps/api/src/better_resume/http/chat.py:151-151: 4/11 evidence lines in window
FAIL  [http] http-06: 「哪些写操作要让 hot 缓存失效」是散在路由里的人际约定（同一行 ×4），没有任何地方强制
        apps/api/src/better_resume/http/interview.py:170-170: 0/5 evidence lines in window
        apps/api/src/better_resume/http/interview.py:284-284: 0/5 evidence lines in window
        apps/api/src/better_resume/http/interview.py:463-463: 0/5 evidence lines in window
        apps/api/src/better_resume/http/interview.py:463-463: 0/5 evidence lines in window
        apps/api/src/better_resume/http/interview.py:222-224: 0/5 evidence lines in window
PART  [http] http-07: http/interview.py:417 的 _resolve_gateway 是 gateway_for 的同签名转调，只为换一个 sc
        apps/api/src/better_resume/http/interview.py:440-442: 0/6 evidence lines in window
        apps/api/src/better_resume/http/interview.py:143-143: 1/6 evidence lines in window
        apps/api/src/better_resume/http/interview.py:267-267: 0/6 evidence lines in window
PART  [http] http-11: POST /sessions/{id}/finish 的行为随服务端开关分叉，并且只在同步分支用 model_ref——参数被静默忽略
        apps/api/src/better_resume/http/interview.py:450-450: 0/5 evidence lines in window
        apps/api/src/better_resume/http/interview.py:430-451: 2/5 evidence lines in window
PART  [http] http-13: 同一份 __all__ 在 http/interview.py 里出现两次（299-305 与 468-476），是编辑残留
        apps/api/src/better_resume/http/interview.py:307-313: 5/11 evidence lines in window
        apps/api/src/better_resume/http/interview.py:491-493: 0/11 evidence lines in window
PART  [interview_engine] IE-01: 失败的答案行与成功的答案行不可区分：同 request_id 重试会被幂等闸门当成「已作答」重放，分数永远拿不回来
        apps/api/src/better_resume/interview_engine/answer_service.py:118-124: 0/22 evidence lines in window
        apps/api/src/better_resume/interview_engine/answer_service.py:368-401: 1/22 evidence lines in window
        apps/api/src/better_resume/interview_engine/answer_repo.py:58-67: 4/22 evidence lines in window
        apps/api/src/better_resume/interview_engine/orm.py:131-132: 2/22 evidence lines in window
        apps/api/tests/interview_engine/test_answer_service.py:234-268: 2/22 evidence lines in window
PART  [interview_engine] IE-07: 同一条「网关返回的 parsed 不是期望类型」防御分支有四种写法，其中两种把模型契约问题报成 404
        apps/api/src/better_resume/interview_engine/answer_service.py:217-228: 0/13 evidence lines in window
        apps/api/src/better_resume/interview_engine/question_service.py:213-214: 0/13 evidence lines in window
        apps/api/src/better_resume/interview_engine/follow_up_service.py:93-98: 2/13 evidence lines in window
        apps/api/src/better_resume/interview_engine/report_service.py:301-302: 0/13 evidence lines in window
PART  [interview_engine] IE-08: ReportService._aggregate 返回无名 dict（6 个键），被 build_report_key / _summari
        apps/api/src/better_resume/interview_engine/report_service.py:213-213: 0/11 evidence lines in window
        apps/api/src/better_resume/interview_engine/report_service.py:269-276: 0/11 evidence lines in window
        apps/api/src/better_resume/interview_engine/report_service.py:65-77: 3/11 evidence lines in window
        apps/api/src/better_resume/interview_engine/report_service.py:280-280: 1/11 evidence lines in window
PART  [interview_engine] IE-09: 三处「留给未来调用者 / 为了让 import 不算未使用」的死代码，带 pragma 所以覆盖率也不会报警
        apps/api/src/better_resume/interview_engine/answer_service.py:405-444: 0/11 evidence lines in window
        apps/api/src/better_resume/interview_engine/report_service.py:428-433: 1/11 evidence lines in window
        apps/api/src/better_resume/interview_engine/answer_repo.py:143-179: 2/11 evidence lines in window
PART  [interview_engine] IE-10: 追问预算 max_follow_up=2 在五处各写一遍，派生路径固定写 2 而不是继承既有预算
        apps/api/src/better_resume/interview_engine/models.py:135-135: 2/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/flow_store.py:37-37: 3/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/question_service.py:275-275: 0/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/restore_service.py:153-156: 3/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/orm.py:180-181: 2/14 evidence lines in window
        apps/api/src/better_resume/http/interview.py:76-76: 2/14 evidence lines in window
PART  [llm_gateway] LG-06: GatewayFactory 协议只声明两个方法，resolver 却按私约动态取用 credential_hint / build_for
        apps/api/src/better_resume/llm_gateway/resolver.py:69-75: 1/11 evidence lines in window
        apps/api/src/better_resume/llm_gateway/resolver.py:91-96: 0/11 evidence lines in window
        apps/api/src/better_resume/llm_gateway/resolver.py:48-56: 0/11 evidence lines in window
        apps/api/src/better_resume/llm_gateway/resolver.py:176-182: 1/11 evidence lines in window
PART  [llm_gateway] LG-07: 「凭证是否齐备 / 缺哪个环境变量」在三个工厂里各写一遍，表达方式还各不相同
        apps/api/src/better_resume/llm_gateway/xingyun_factory.py:30-41: 7/17 evidence lines in window
        apps/api/src/better_resume/llm_gateway/dashscope_app_factory.py:25-29: 0/17 evidence lines in window
        apps/api/src/better_resume/llm_gateway/resolver.py:91-106: 1/17 evidence lines in window
PART  [llm_gateway] LG-10: SceneResolver.loads 是仅供测试断言的公开属性（生产对象上挂着缓存计数器）
        apps/api/src/better_resume/llm_gateway/resolver.py:141-146: 0/13 evidence lines in window
        apps/api/tests/llm_gateway/test_scene_resolver.py:100-109: 0/13 evidence lines in window
        apps/api/tests/llm_gateway/test_scene_binding_propagation.py:92-92: 1/13 evidence lines in window
PART  [llm_gateway] LG-12: 「出厂默认绑定是 openai_compat/deepseek-flash」在 resolver 常量与迁移种子里各写一份，is_defau
        apps/api/src/better_resume/llm_gateway/resolver.py:28-30: 2/17 evidence lines in window
        apps/api/src/better_resume/llm_gateway/resolver.py:236-241: 0/17 evidence lines in window
        apps/api/migrations/versions/9f2c1a7b5d31_scene_bindings.py:21-29: 10/17 evidence lines in window
PART  [web] web-07: 答题幂等键 request_id 每次调用现生成，真正的幂等靠一个 250ms 只在前端存在的时间窗兜底
        apps/web/src/interview/useInterviewRoom.ts:9-9: 1/6 evidence lines in window
        apps/web/src/interview/useInterviewRoom.ts:67-71: 3/6 evidence lines in window
        apps/web/src/interview/useInterviewRoom.ts:76-80: 0/6 evidence lines in window
STRUCT http/http-13: apps/api/src/better_resume/http/interview.py:491-493 outside 1..490

1 structural problem(s) in 10 unit(s)
EXIT=1
```

重锚后的读数（同一份代码，工作区的 units）：

```bash
uv run --project apps/api python scripts/verify_audit_evidence.py --strict; echo "EXIT=$?"
```

```text
verifiable: 122  partial: 0  unverifiable: 0
EXIT=0
```

判绿口径与基线一致：verifiable 122（条目数未因重锚增减），partial 0 / unverifiable 0 / 结构问题 0。

### 2 层内 pytest 审计用例

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t17_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t17_audit.xml
uv run pytest tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence -q --junitxml=/tmp/t17_audit.xml
```

```text
.                                                                        [100%]
pytest_exit=0
junit: {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '1', 'time': '0.108', 'timestamp': '2026-10-17T13:07:34.613167+08:00', 'hostname': 'LAPTOP-V77BKNTH'}
```

### 3 scripts 层（T8 接线的收口读数）

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
bash scripts/verify.sh --layer scripts; echo "verify_exit=$?"
```

```text
[1/12] bash scripts/verify_secrets.sh --selftest
selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）
/tmp/tmp.fZxuKzTzO6/bad/sample.env:2: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:3: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:4: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:5: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:6: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:7: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:8: [已打码]
/tmp/tmp.fZxuKzTzO6/bad/sample.env:9: [已打码]
bad=detected (8/8 hits)
selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）
good=clean (0 hits)
selftest 3/3: 仓库当前必须干净
repo=clean (0 hits in 619 files)
selftest=PASS
[2/12] bash scripts/verify_secrets.sh
repo=clean (0 hits in 619 files)
[3/12] bash scripts/verify_docs_hygiene.sh --selftest
ok   [必红] 84f622b 手测轮次样本：命中 2 处
ok   [必红] 禁词 之前是：命中 1 处
ok   [必红] 禁词 第 N 轮：命中 1 处
ok   [必红] 禁词 已废弃：命中 1 处
ok   [必红] 禁词 曾经踩过：命中 1 处
ok   [必红] 禁词 已作废：命中 1 处
ok   [必绿] CODING_STANDARDS 不适用模板措辞
ok   [必绿] 围栏代码块内引证
ok   [必绿] 行内 code 内引证
ok   [必绿] AGENTS.md 硬规则 2 三行原文按清单豁免（3 行共 5 个禁词命中）
ok   [必红] 豁免只认原文：改一个字符即失效：命中 1 处
自检通过：11/11 个用例符合预期
[4/12] bash scripts/verify_docs_hygiene.sh
扫描 511 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
[5/12] bash scripts/verify_citations.sh --selftest
PASS 自检：好样本（直配 + 唯一短名） —— 退出 0
PASS 自检：不存在的路径 —— 退出 1
PASS 自检：行号越界 —— 退出 1
PASS 自检：同名多文件的短名 —— 退出 1
PASS 自检：围栏内的坏引证放过 —— 退出 0
PASS 自检：围栏外同款坏引证抓住 —— 退出 1
自检通过 6/6：好样本绿；不存在路径 / 行号越界 / 同名多文件三种坏样本都被判失败；围栏内放过、围栏外同款抓住
[6/12] find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
引证 104（直配 69，短名兜底 35）解析成功 104 失败 0
[7/12] bash scripts/ticket_frontier.sh --selftest
ok   frontier：跳过 resolved / claimed / 被未结题票阻塞，取 T4：T4 T4-free.md 四号票
ok   check：合法树退出码：0
ok   check：缺 Status 行退出码：1
ok   check：缺 Status 行点名文件与原因：yes
ok   check：Blocked by 悬空退出码：1
ok   check：Blocked by 悬空点名文件与票号：yes
ok   check：同号重名退出码：1
ok   check：同号重名点名两个文件：yes
selftest: 8 项断言，失败 0 项
[8/12] bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
OK docs/tickets/p15-agent-friendly-architecture：结构校验通过（18 张票）
[9/12] cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
........................................................................ [ 71%]
.............................                                            [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /root/better resume/apps/api/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /root/better resume/apps/api/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
101 passed, 2 warnings in 7.23s
[10/12] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo 'shell syntax ok'
shell syntax ok
[11/12] uv run --project apps/api python scripts/check_scripts.py
script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[12/12] uv run --project apps/api python scripts/verify_audit_evidence.py --structural
structure ok: 10 units / 122 issues / 341 citations
ALL PASS (12 commands) -- evidence: var/evidence/20261017T051617Z-scripts
```

### 4 权威全量（新鲜隔离库 br_t17_verify，串行独占）

建库（跑完 drop，见未验证项）：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run python /tmp/mkdb_t17.py   # asyncpg 连 better_resume 库：DROP DATABASE IF EXISTS br_t17_verify; CREATE DATABASE br_t17_verify
```

```text
br_t17_verify created
```

```bash
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t17_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t17_full2.xml
uv run pytest -q --junitxml=/tmp/t17_full2.xml; echo "pytest_exit=$?"
python3 -c "import xml.etree.ElementTree as ET; r=ET.parse('/tmp/t17_full2.xml').getroot(); ts=r if r.tag=='testsuite' else r.find('testsuite'); print('junit:', dict(ts.attrib))"
```

```text
pytest_exit=0
junit: {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '1009', 'time': '87.365', 'timestamp': '2026-10-17T13:11:55.955762+08:00', 'hostname': 'LAPTOP-V77BKNTH'}
```

同库此前还跑过一次 1009 / 0 / 0 / 0（time 78.676），但那次与 scripts 层 pytest 同跑；为满足「串行」口径，先 DROP/CREATE 新库再独占重跑，上表是独占读数。

## 引证改动清单

只改 `where` 的文件:行号/范围与 5 处「被重构改名或删除、原样摘录已不可复现」的证据行；title / why / fix 一字未动。

| 审计条目 | 改前锚点 | 改后锚点 | 依据 |
| --- | --- | --- | --- |
| http-01 | `http/scenes.py:57` | `http/chat.py:137` | scenes.py 的 PUT 端点已把会话交给 `SceneResolver.bind()`，该文件不再有 `request.app.state.session_factory`；换成另一个真实站点，并同步该条证据行（`as session:` 形态全仓库已不存在） |
| http-03 | `interview.py:432` | `interview.py:448-450` | ReportService 内联构造被 T13 加了 `hot_state=` 并拆成三行，证据行同步成现在这三行原文 |
| http-06 | `interview.py:170/284/463/463/222-224` | 三个写服务的调用点 + `hot_state.py:126-137` | 引证对象（`_invalidate_hot` 助手与 4 处调用）已被 T13 删除 → 记 `fix_record`，引证改指替代机制 |
| http-07 | `440-442` / `267` | `433-435` / `260` | 行位移 |
| http-11 | `450` | `443` | 行位移 |
| http-13 | `491-493` | `482-489` | T13 在 interview.py 净删 9 行，`__all__` 落到 482-490；原锚点越界（结构级 STRUCT） |
| IE-01 | `answer_service.py:118-124` | `126-132` | 行位移 |
| IE-07 | `217-228` / `213-214` / `301-302` | `233-236` / `216-218` / `305-307` | 行位移 |
| IE-08 | `213` / `269-276` / `280` | `218` / `280-288` / `292` | 行位移（`_aggregate` 与 `missing=` 各自下移） |
| IE-09 | `405-444` / `428-433` | `451-452` / `433-438` | 死代码块下移 |
| IE-10 | `question_service.py:275` | `277-283` | 行位移 |
| LG-06 | `69-75/91-96/48-56/176-182` | `64-70/86-94/193-194/176-183` | 协议块与实现下移；`_call` 助手已被 T12 删除，引证不再指向它；证据块按当前代码重写（`config_status` 进协议、resolver 按协议调用、`build_for_model` 仍是私约） |
| LG-07 | `dashscope:25-29` | `dashscope:26-30` | T12 把 `is_configured/credential_hint` 合成 `config_status`，证据块按当前两处实现重写 |
| LG-10 | `resolver:141-146` / `test:100-109` | `129-134` / `128-137` | 行位移（`loads` 属性与它的用例） |
| LG-12 | `resolver:236-241` | `246-249` | `views()` 里 `is_default=` 下移 |
| web-07 | `useInterviewRoom.ts:76-80` | `78-82` | submit 调用块下移 |

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 证据块里被重构改名/删除的原文摘录按当前代码刷新（http-01 一处、http-03 一行、http-06 整块、LG-06 整块、LG-07 整块） | 逐字级门禁的判据是「被引窗口里能找到摘录原文」；代码被 T12/T13 改名或删除后，窗口怎么挪都对不上。只重锚行号而不刷新摘录，就会得到「门禁绿但引证撒谎」——正是 P09/T11 要消灭的形态（T11 出票方裁决口径） | 没有改任何 title / why / fix；没有新增或删除引证条目；没有把引证的语义范围做任何放宽 |
| http-06 记 `fix_record`（status=fixed） | 红线点名授权（`_invalidate_hot` 已被 T13 删除），且 T13 的 `test_every_write_path_drops_the_warm_hot_view` 真钉住了「写路径自带失效」 | 没有顺手给其它「看起来也修了一半」的条目记 fix_record |
| LG-06 只重锚 + 刷新摘录，不记 fix_record | 它的结论里 `credential_hint` 半边确已被 T12 的 `config_status` 消掉，但 `build_for_model` 仍是私约（`resolver.py:180` 的 getattr 还在）——不是「确已被修复」，记 fixed 会撒谎。按票面「代码与审计结论真的不一致时停下来报」，交回出票方裁决 | 没有改 LG-06 的 why（那段仍写着旧形态的 73/91 行与 `_call` 兜底）；没有替出票方决定该条该记 fixed 还是 fixing |
| 只重锚门禁点名的 16 条引证（PART / FAIL，含其中越界的那条） | 未点名的窗口可能同样过期、只是被弱匹配兜住而判绿；逐条语义复核不在本票验收口径内，扩大范围会越出「引证锚点」的写入面 | 没有系统复核全部 341 条引证的语义新鲜度（见未验证项 1） |
| 用脚本既有 `--units` 开关指向 HEAD 还原的临时目录来演示「红」 | units 已被我改绿，无法在原地重放红；`--units` 只换数据目录，判定代码与代码版本都不变 | 没有用 git stash / 回退工作区来制造红（会碰到 p14 与并发票的在飞改动） |

## 未验证项

1. **未点名的引证没有逐条语义复核**：`--strict` 的判据是「窗口里至少命中一条摘录」，弱行（`)`、`name`、`...` 这类）能让已经过期的窗口照样判绿（例：LG-09 引 `resolver.py:236-241`，那 6 行现在是 `views()` 的 `status = (...)` 段，判绿靠弱匹配兜住）。本票处理的是门禁点名的 16 条（15 PART + 1 FAIL，其中 http-13 另触发 1 条结构级越界），没有对全部 341 条引证做「窗口是否仍指同一段知识」的人工复核。
2. **标题里内嵌的旧行号与计数保持原样**（http-07 的 `417`、http-13 的 `299-305 与 468-476`、http-01 的 `29 处`、IE-07/IE-08/IE-10 的旧行号）：红线要求不动 issue 描述，判绿也不读标题，故只在此记录漂移，未改。
3. **`docs/audit/MODULE-AUDIT.html` 未重建**：它是 units 的派生渲染产物，重建会写本票写入面以外的文件；HTML 里的行号与 fix_record 块仍是旧读数。
4. **「重锚前红」的口径**：它演示的是「HEAD 版 units 相对当前工作区代码过期」，不等价于「相对 HEAD 代码过期」——HEAD 代码下 units 是绿的（基线 122/0/0）。
5. **只跑了后端 pytest 全量**：contract / coverage / deploy / e2e / fault / soak / real 各层与前端（`pnpm -C apps/web test --run`）未跑；本票未动前端与 REST 模型。
6. **Redis 仍是共享实例**：全量读数在隔离 Postgres（`br_t17_verify`）上取，但 `BR_REDIS_URL` 指向共享 `127.0.0.1:6379/0`，本票没有给 Redis 侧做隔离；隔离库跑完已 DROP。
