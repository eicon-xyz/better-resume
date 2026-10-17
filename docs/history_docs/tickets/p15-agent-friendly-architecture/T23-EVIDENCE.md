# T23 验收证据：FlowStateMissing 的 HTTP 错误语义

## 意图复述

1. 缺 `interview_flow_state` 行的会话答题时，`FlowStateMissing` 只能落到 `InterviewEngineError` 的通配 handler（422 + 只有 `detail`、没有 `kind`），客户端分不出「你没登录」「依赖不可用」「数据缺失」。
2. 本票在 `main.py` 既有的 exception-handler / `{"detail", "kind"}` 通道上给 `FlowStateMissing` 单加一条映射：明确状态码 + kind，响应体点名缺的是 flow state；不动 REST 模型（openapi.json / schema.d.ts），不引依赖。
3. 先红后绿：先在答题面的 HTTP 用例上演示现状拿不到目标状态码与 kind（红），再落映射（绿），并证明把 flow 行补回后答题恢复正常。

## 红演示：改映射前

红取自改映射前的运行；下面同时给出可复跑的等价复现（把 `main.py` 临时换回 HEAD 版本、跑完按 md5 换回），两者读数一致。

复现命令：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t23_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
cp src/better_resume/main.py /tmp/t23-main-new.py
git show HEAD:apps/api/src/better_resume/main.py > src/better_resume/main.py   # 换成改映射前的版本
rm -f /tmp/t23-red.xml
.venv/bin/python -m pytest tests/test_interview_answers_api.py -q --junitxml=/tmp/t23-red.xml -k missing_flow_state
cp /tmp/t23-main-new.py src/better_resume/main.py                            # 换回
md5sum /tmp/t23-main-new.py src/better_resume/main.py
```

原始输出（节选，逐字）：

```text
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_missing_flow_state_is_a_named_server_fault_and_recovers _________

    def test_missing_flow_state_is_a_named_server_fault_and_recovers(
        client: TestClient, gateway, migrated_database: str
    ) -> None:
        """A vanished flow row is our own data fault: not 401 ("you never logged in") and not
        503 ("the dependency is down"). It must say which state is missing, never score silently,
        and answering works again once an operator puts the row back."""
        login(client)
        fake = gateway(FakeGateway(score=84.0))
        session_id = prepare(client, fake)
    
        wipe_flow_state(migrated_database, session_id)
        failed = answer(client, session_id, "1", "ans-no-flow")
    
>       assert failed.status_code == 500, failed.text
E       AssertionError: {"detail":"flow state missing for session 98620018-73cf-4aae-b63f-053f1ece5441"}
E       assert 422 == 500
E        +  where 422 = <Response [422 Unprocessable Entity]>.status_code

tests/test_interview_answers_api.py:317: AssertionError
=========================== short test summary info ============================
FAILED tests/test_interview_answers_api.py::test_missing_flow_state_is_a_named_server_fault_and_recovers
```

读数（junitxml）：`/tmp/t23-red.xml tests=1 failures=1`；`red exit=1`；换回后 `md5sum` 与改动版一致（f8e29cfc295c85dab2816304f7605ea5）。

红的样子（同时修正票面前提）：`FlowStateMissing` 继承 `InterviewEngineError`，现状不是「裸错穿到 500」，而是被通配 handler 收成 **422 + 只有 `detail`、没有 `kind`** —— 与「题目不存在」「非法状态迁移」这类客户端错误同码同形，客户端无从分出「数据缺失」。红点即「422 而非目标状态码、且响应无 kind」。

## 绿：映射后

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t23_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t23-green.xml
.venv/bin/python -m pytest tests/test_interview_answers_api.py -q --junitxml=/tmp/t23-green.xml -k missing_flow_state
echo "green exit=$?"
```

```text
.                                                                        [100%]
green exit=0
```

读数（junitxml）：`/tmp/t23-green.xml tests=1 failures=0 errors=0 skipped=0`。

用例本身钉住四件事：`status_code == 500`、`payload["kind"] == "flow_state_missing"`、`detail` 里同时出现 session id 与 `flow state missing`（点名缺的是什么）、以及 `fake.calls == 1`（答题没有静默评过分、没有吞掉）；删行后再把行补回（`FlowStateStore.initialize`，status=asking、current_question_no="1"），同一个 `request_id` 重发拿到 201 + 84.0 分 + 下一题 "2"，即恢复。

## 定向 pytest 与 ruff

```bash
cd '/root/better resume/apps/api'
.venv/bin/python -m pytest -q --junitxml=/tmp/t23-targeted.xml \
  tests/test_interview_answers_api.py tests/test_interview_api.py \
  tests/test_interview_report_api.py tests/interview_engine tests/test_openapi_export.py
echo "targeted exit=${PIPESTATUS[0]}"
```

```text
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
..........................................................               [100%]
targeted exit=0
```

读数（junitxml）：`/tmp/t23-targeted.xml tests=274 failures=0 errors=0 skipped=0`（全库可达，没有静默 skip）。

```bash
cd '/root/better resume/apps/api'
uv run ruff format --check src/better_resume/main.py tests/test_interview_answers_api.py; echo "format check exit: $?"
uv run ruff check src/better_resume/main.py tests/test_interview_answers_api.py; echo "lint exit: $?"
```

```text
2 files already formatted
format check exit: 0
All checks passed!
lint exit: 0
```

## REST 模型未动（只读比对）

`export_openapi.py` 会写 `openapi.json`（红线不许），所以改用只读比对：内存里现生成 schema 与已提交文件逐字节比。

```bash
cd '/root/better resume/apps/api'
.venv/bin/python -c 'import json; from better_resume.main import create_app; from better_resume.settings import Settings; app = create_app(Settings(_env_file=None)); live = app.openapi(); committed = json.load(open("openapi.json", encoding="utf-8")); print("openapi identical to committed file:", json.dumps(live, sort_keys=True) == json.dumps(committed, sort_keys=True))'
git -C '/root/better resume' status --porcelain -- apps/api/openapi.json apps/web/src/api/schema.d.ts
```

```text
openapi identical to committed file: True
（git status 无输出 = openapi.json / schema.d.ts 未动）
```

## 隔离库全量读数

```bash
cd '/root/better resume/apps/api'
.venv/bin/python -m pytest -q --junitxml=/tmp/t23-full.xml tests
echo "full exit=${PIPESTATUS[0]}"
```

```text
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
full exit=1
```

读数（junitxml）：`/tmp/t23-full.xml tests=1018 failures=1 errors=0 skipped=0`；红的那 1 例是审计引证逐字级门禁，见「未验证项」第 1 条（基线已红，且它的重锚是 T22 的范围）。

## 实现决定交代

| 决策点 | 选择 | 理由与代价 |
| --- | --- | --- |
| 映射放哪 | `main.py` 装配层：`app.add_exception_handler(FlowStateMissing, _flow_state_missing)`；`flow_store.py`、`http/interview.py` 不动 | 「既有 errors 通道」就是装配层按异常类逐条注册（`_not_found`/`_conflict`/`_unprocessable`/网关四档），加一条最省；`require`/`mutate` 的调用点全在 `AnswerService` 内（`grep` 确认），注册一次覆盖答题及其回滚/落库路径。代价：pytest 面只有 HTTP 用例能钉它 |
| 状态码 500 | 500，且**不带** `Retry-After` | 调用方已登录、会话与题目都在，缺的是我们自己持久化的 flow 行 —— 4xx 会把服务端缺数据说成请求有问题：401 是「你没登录」、404 会谎称会话/题目不存在、409/422 与既有的「你答错题了」「非法迁移」同码；503+Retry-After 是「依赖不可用，等会儿再来」，而重发必然同样失败，给重试头是假承诺。代价：前端 `kindForStatus(500)` 归为 `server`，`describeApiError` 回落到 `detail` 原文（英文、含 session id） |
| 错误 kind | `"flow_state_missing"` | 与网关四档（`timeout`/`unavailable`/`invalid`/…）同形不同值，客户端不必解析 detail 就能分类；它与「未登录」（401）「依赖不可用」（503 + kind=unavailable）在状态码与 kind 两个维度都可区分 |
| 响应体形状 | 只有 `detail` + `kind`，不加 `missing` 之类的第二个字段 | 与 `_unprocessable`/`_conflict`/`_gateway_*` 完全同形 = 确实走同一条通道、没有第二套；「缺的是什么」由 detail 的 `flow state missing for session <id>` 点名，用例把这句与 session id 都钉住了。代价：这句文案成了事实契约，改 `flow_store` 的报错文案要同步改用例 |
| 用例落在哪 | `tests/test_interview_answers_api.py`（答题面 HTTP 用例），改库用自有 engine + `NullPool` | 票面要的就是「缺行答题」这条路径；app 的连接池属于 TestClient 的事件循环，另开 NullPool engine 是本仓既有手法（`test_restore_report.py` 同款）。代价：新增两个测试辅助函数（删行/补行） |
| 是否补修复路径 | 不补 | 票面「不许把缺行静默重建」是 T19 刚拆掉的东西；本票只给语义。补回行后答题恢复由用例证明「语义明确、不是死路」 |

## 隔离库（br_t23_verify）

上述读数一律在这一支隔离库上取（P15-1 口径）；开跑前创建、收工 drop。

```bash
cd '/root/better resume/apps/api'
.venv/bin/python - <<'PY'
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        user="better_resume", password="better_resume",
        host="127.0.0.1", port=5433, database="postgres",
    )
    await conn.execute("DROP DATABASE IF EXISTS br_t23_verify")
    await conn.execute("CREATE DATABASE br_t23_verify")
    await conn.close()
    print("br_t23_verify ready")

asyncio.run(main())
PY
```

```text
br_t23_verify ready
```

收工 drop 的原始输出：

```bash
cd '/root/better resume/apps/api'
.venv/bin/python - <<PY
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        user="better_resume", password="better_resume",
        host="127.0.0.1", port=5433, database="postgres",
    )
    await conn.execute("DROP DATABASE br_t23_verify")
    rows = await conn.fetch("select datname from pg_database order by datname")
    print("dropped; databases now:", [r["datname"] for r in rows])
    await conn.close()

asyncio.run(main())
PY
```

```text
dropped; databases now: ['better_resume', 'better_resume_demo', 'postgres', 'template0', 'template1']
```

## 未验证项

1. **全量 1018 例里 1 红，且基线已红**：`tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`（审计引证逐字级门禁）。把 `main.py` 换回 HEAD、其余工作区不动时的读数是 `verifiable: 121 partial: 1 unverifiable: 0`（那一例 partial 是 IE-10 引 `restore_service.py:153-156`，T19 移位波及项）。加了本票的 16 行后读数 `verifiable: 118 partial: 2 unverifiable: 2`：新增的红全落在引证到 `main.py` 的行上 —— http-09 与 so-04 引 `main.py:204-204`、identity_jobs-03 引 `main.py:52-60` 与 `main.py:217-217`。**本票红线不许动 `docs/audit/`，重锚是 T22（`Blocked by: T16, T18, T19, T21, T23`，唯一写入路径 `docs/audit/units/`）的范围**：T22 需要把上述 `main.py` 锚点整体后移 16 行（`52-60 → 53-61`、`204 → 220`、`217 → 233`）并同步 evidence 摘录。
2. **没跑**：`bash scripts/verify.sh --layer all / coverage / scripts`；前端用例与契约三件套的生成命令（`export_openapi.py` / `gen:api` 会写文件，红线不许，改用上面那次只读逐字节比对）；`--layer real` 的真机探针与演练。
3. **并发写面**：工作区里另有其它票未提交的改动（`apps/api/src/**` 多个文件、`apps/api/tests/**`、`docs/audit/units/*.json` mtime 13:07）。本票落盘只有三个文件：`apps/api/src/better_resume/main.py`、`apps/api/tests/test_interview_answers_api.py`、本文件。
4. **只映射了 HTTP 面**：worker 侧不碰 flow store（`grep` 的 `require`/`mutate` 调用点全在 `AnswerService`，经答题端点汇入），没有 worker 端演练。
5. **前端未验证**：红线不许动 `apps/web`，所以 `500 → kindForStatus = "server"`、`describeApiError` 回落 `detail` 只做了代码阅读，没有跑前端用例，也没有为这个 kind 写中文文案。
6. **`MODULE-AUDIT.html` 未重建**（生成产物，属 T22）。
