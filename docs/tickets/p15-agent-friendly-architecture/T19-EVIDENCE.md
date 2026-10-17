# T19 证据：RestoreService.restore 读路径写库（P15-2）

## 意图复述

- 我理解这票解决什么：`RestoreService.restore` 在 `interview_flow_state` 缺行时用 `FlowStateStore.initialize` 把派生态写回库；无题会话因此先落一行 `total_questions=0` 的流状态，随后 `QuestionService._persist` 的 `initialize` 插同一主键（`session_id`）直接 `IntegrityError`——读路径替出题写下了它自己不认识的行。
- 我怎么做，到文件粒度：`interview_engine/restore_service.py` 的 `_derive` 改成只在内存里构造 `FlowState`（不碰 session、不提交）；`interview_flow_state` 行的创建责任仍唯一留在出题写入方（`QuestionService._persist` → `FlowStateStore.initialize`）；用例写在 `tests/interview_engine/test_restore_report.py`——新增 restore→出题交接用例，并把「派生态回写」的旧断言改成「读路径不写」。
- 我不做什么：不改 HTTP 面与 REST 模型、不引依赖、不动 p14、不 commit/push/开 PR；不改 `flow_store.py` 的写 API，也不动 `answer_service`/`report_service`。

## 红-绿（先按票演示红）

红用的坏输入 = 改动前的实现（`restore_service.py` 仍是 HEAD 版本，`_derive` 走 `FlowStateStore.initialize` 写回）；两条用例一起跑，各钉一个形态：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t19_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t19-red.xml
uv run pytest -q tests/interview_engine/test_restore_report.py::test_restore_derives_flow_state_when_the_row_is_gone tests/interview_engine/test_restore_report.py::test_restore_leaves_the_flow_row_to_the_generation_writer --junitxml=/tmp/t19-red.xml
```

原始输出（逐字：failure body 取自 `/tmp/t19-red.xml`，junit 读数由同一支 xml 统计；中间若干栈帧以 `...` 显式省略）：

```text
##### test_restore_derives_flow_state_when_the_row_is_gone

    assert view.derived is True
    assert view.current_question_no == "3"
    assert view.answered == 2
    # Re-deriving is idempotent: the second read sees the same thing.
>   assert (again.derived, again.current_question_no, again.answered) == (True, "3", 2)
E   AssertionError: assert (False, '3', 2) == (True, '3', 2)
E     
E     At index 0 diff: False != True
E     Use -v to get more diff

tests/interview_engine/test_restore_report.py:167: AssertionError

##### test_restore_leaves_the_flow_row_to_the_generation_writer
...
>                   raise translated_error from error
E                   sqlalchemy.exc.IntegrityError: (sqlalchemy.dialects.postgresql.asyncpg.IntegrityError) <class 'asyncpg.exceptions.UniqueViolationError'>: duplicate key value violates unique constraint "interview_flow_state_pkey"
E                   DETAIL:  Key (session_id)=(9c7fb6e1-bf3f-4500-9ec7-b3ae3072114e) already exists.
E                   [SQL: INSERT INTO interview_flow_state (session_id, status, current_index, current_question_no, total_questions, follow_up_count, max_follow_up, version, updated_at) VALUES ($1::VARCHAR, $2::VARCHAR, $3::INTEGER, $4::VARCHAR, $5::INTEGER, $6::INTEGER, $7::INTEGER, $8::INTEGER, $9::TIMESTAMP WITH TIME ZONE)]
E                   [parameters: ('9c7fb6e1-bf3f-4500-9ec7-b3ae3072114e', 'asking', 0, '1', 3, 0, 2, 1, datetime.datetime(2026, 10, 17, 6, 18, 56, 386813, tzinfo=datetime.timezone.utc))]
E                   (Background on this error at: https://sqlalche.me/e/20/gkpj)

.venv/lib/python3.12/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py:797: IntegrityError

=========================== short test summary info ============================
FAILED tests/interview_engine/test_restore_report.py::test_restore_derives_flow_state_when_the_row_is_gone
FAILED tests/interview_engine/test_restore_report.py::test_restore_leaves_the_flow_row_to_the_generation_writer
{'tests': 2, 'failures': 2, 'errors': 0, 'skipped': 0}
```

两条红各自钉住的形态：

- 第二条就是票面点名的形态：restore 先把 flow 行写进库，出题的 `initialize` 再插同一主键 → `duplicate key value violates unique constraint "interview_flow_state_pkey"`（参数里 `total_questions=3`、`current_question_no='1'` 就是出题要建的那一行）。
- 第一条钉的是「读路径改了持久状态」：第一次 restore 落行，第二次 restore 读到持久行，`derived` 由 True 变 False——同一个只读调用前后给出两种派生来源，幂等被写库破坏。改版后这条用例的收尾断言换成「读后仍无行 + 两次读一致」，前三个断言行逐字未改。

## 验收命令与原始输出

### 1. 改后：整文件转绿

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t19_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t19-file.xml
uv run pytest -q tests/interview_engine/test_restore_report.py --junitxml=/tmp/t19-file.xml
python3 - <<'PY'
import xml.etree.ElementTree as ET
root=ET.parse('/tmp/t19-file.xml').getroot()
suites=[root] if root.tag=='testsuite' else list(root)
print('JUNIT', {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')})
PY
```

```text
11 passed, 2 warnings in 6.84s
JUNIT {'tests': 11, 'failures': 0, 'errors': 0, 'skipped': 0}
```

### 2. 幂等：相关面定向集连跑两遍（同一支命令，只换 junit 文件名）

```bash
cd '/root/better resume/apps/api'
# 同上四个 env
for i in 1 2; do
  rm -f /tmp/t19-group-final-$i.xml
  uv run pytest -q tests/interview_engine/test_restore_report.py tests/interview_engine/test_question_service.py \
    tests/interview_engine/test_answer_service.py tests/test_hot_state.py tests/test_interview_api.py \
    tests/test_interview_answers_api.py tests/test_interview_report_api.py --junitxml=/tmp/t19-group-final-$i.xml
done
```

```text
/tmp/t19-group-final-1.xml {'tests': 75, 'failures': 0, 'errors': 0, 'skipped': 0}
/tmp/t19-group-final-2.xml {'tests': 75, 'failures': 0, 'errors': 0, 'skipped': 0}
```

用例内部的幂等断言（第二条 restore 与第一条同源同值）见 `test_restore_derives_flow_state_when_the_row_is_gone`。

### 3. 票面第 3 条：`flow_state` 命中逐条归属

```bash
cd '/root/better resume'
grep -rn "flow_state" apps/api/src/better_resume/interview_engine
```

```text
apps/api/src/better_resume/interview_engine/orm.py:158:    __tablename__ = "interview_flow_state"
apps/api/src/better_resume/interview_engine/orm.py:162:            name="ck_interview_flow_state_status",
apps/api/src/better_resume/interview_engine/restore_service.py:155:        logger.warning("flow_state_derived", session_id=session_id, current=current_no)
grep: apps/api/src/better_resume/interview_engine/__pycache__/restore_service.cpython-310.pyc: binary file matches
grep: apps/api/src/better_resume/interview_engine/__pycache__/restore_service.cpython-312.pyc: binary file matches
grep: apps/api/src/better_resume/interview_engine/__pycache__/orm.cpython-312.pyc: binary file matches
grep: apps/api/src/better_resume/interview_engine/__pycache__/orm.cpython-310.pyc: binary file matches
```

三条源码命中没有一条是写点：列名兜底的是表名/约束名字符串与一条派生日志。表行的真实读写要用 ORM 行类名才看得见，逐条归属如下（同一支 grep 的第二发：`grep -rn "InterviewFlowStateRow" apps/api/src/better_resume`）：

| 命中 | 归属 |
| --- | --- |
| `apps/api/src/better_resume/interview_engine/orm.py:157` `class InterviewFlowStateRow` | 表映射定义（行类本体），非读写点。 |
| `apps/api/src/better_resume/interview_engine/orm.py:158`、`apps/api/src/better_resume/interview_engine/orm.py:162` | 表名 `interview_flow_state` 与约束名 `ck_interview_flow_state_status`，非读写点。 |
| `flow_store.py:43` `row = InterviewFlowStateRow(...)` | **唯一创建点**：`FlowStateStore.initialize` 的 INSERT。全仓唯一调用方是 `question_service.py:277`（`QuestionService._persist`，出题写入方）——本票从 `restore_service.py` 删掉的正是第二个调用方。 |
| `flow_store.py:80` `update(InterviewFlowStateRow)` | 状态推进点：`FlowStateStore.mutate` 的 CAS UPDATE，所有者是答题/追问路径（`answer_service.py:147/335/426`）。读路径不经过它。 |
| `flow_store.py:105`、`flow_store.py:108` | `_fetch` 的 SELECT，读点（`load`/`require`/`mutate` 共用）。 |
| `flow_store.py:113` | 行 → `FlowState` 的映射，非读写点。 |
| `restore_service.py:64` | 读点：`FlowStateStore(db).load(session_id)`，只读；缺行时走下一行的内存派生。 |
| `restore_service.py:155` | `flow_state_derived` 告警日志，非写点。 |
| `__pycache__/*.pyc`（4 个二进制命中） | 旧字节码，非源码。 |

### 4. 全量（隔离库 br_t19_verify）

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t19_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t19-full.xml
uv run pytest -q --junitxml=/tmp/t19-full.xml
```

```text
=========================== short test summary info ============================
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
JUNIT {'tests': 1017, 'failures': 1, 'errors': 0, 'skipped': 0}
```

唯一失败是 docs 审计逐字级门禁（仓级 gating，写入面在 `docs/audit/units/*.json`，本票红线之外）。它是本票造成的行位移，归因与重锚位置见「未验证项」第 1 条。

### 5. 本票改动面 ruff

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run ruff format --check src/better_resume/interview_engine/restore_service.py tests/interview_engine/test_restore_report.py; echo "FORMAT_EXIT=$?"
uv run ruff check src/better_resume/interview_engine/restore_service.py tests/interview_engine/test_restore_report.py; echo "CHECK_EXIT=$?"
```

```text
2 files already formatted
FORMAT_EXIT=0
All checks passed!
CHECK_EXIT=0
```

### 6. 文档门禁自查（证据文件写完后跑）

```bash
cd '/root/better resume'
bash scripts/verify_docs_hygiene.sh; echo "hygiene exit=$?"
bash scripts/verify_citations.sh docs/tickets/p15-agent-friendly-architecture/T19-EVIDENCE.md; echo "citations exit=$?"
```

```text
扫描 524 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
hygiene exit=0
引证 15（直配 3，短名兜底 12）解析成功 15 失败 0
citations exit=0
```

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| `_derive` 只构造内存 `FlowState`，不落库、不提交 | 票面给的两条路（派生态只读 / 由唯一写入方创建）在既有会话上落在同一处：`interview_flow_state` 行只在出题那一刻才有意义，restore 回写等于凭空多出第二个创建者——主键冲突就是从这里来的 | 没给 `FlowStateStore.initialize` 加「行已存在就跳过」的兜底：那只是把读路径的写变成幂等写，读路径仍在写库；也没动 `flow_store.py` 的 CAS 写 API |
| 把旧用例的「回写」断言改成「读后仍无行 + 两次读一致」 | 那条断言写的正是要修的行为；改后同一个用例同时钉住「读路径不写库」与「重复派生不漂」，前三个断言行逐字保留 | 没删这条用例，也没另建文件 |
| 新用例落在 `tests/interview_engine/test_restore_report.py` | 票面点名「restore/出题交接缝与其用例」；`QuestionService.generate` 是唯一能复现主键冲突的调用点（无题会话 restore 之后出题） | 没动 `test_hot_state.py` 里同走 restore 的用例：它只断言热层命中/回退，不受本票影响 |
| `_derive` 里的 `max_follow_up=2` 字面量原样保留 | 它是 IE-10 记录的另一条重复（同一常量在五处各写一遍），改它属另一张票的范围 | 没把 2 提成常量或搬进 settings |

## 未验证项

1. **全量不是全绿：1017 个用例里 1 个红，且这次是本票的行位移造成的**——`docs/audit/units/interview_engine.json` 的 IE-10 引用了 `restore_service.py:153-156`（原文摘录命中 `153: return await FlowStateStore(db).initialize(` 与 `156: max_follow_up=2,`），本票把派生路径改成内存构造后该窗口归零：

   ```bash
   cd '/root/better resume'
   apps/api/.venv/bin/python scripts/verify_audit_evidence.py --strict; echo "AUDIT_EXIT=$?"
   ```

   ```text
   PART  [interview_engine] IE-10: 追问预算 max_follow_up=2 在五处各写一遍，派生路径固定写 2 而不是继承既有预算
           apps/api/src/better_resume/interview_engine/models.py:135-135: 2/14 evidence lines in window
           apps/api/src/better_resume/interview_engine/flow_store.py:37-37: 3/14 evidence lines in window
           apps/api/src/better_resume/interview_engine/question_service.py:277-283: 2/14 evidence lines in window
           apps/api/src/better_resume/interview_engine/restore_service.py:153-156: 0/14 evidence lines in window
           apps/api/src/better_resume/interview_engine/orm.py:180-181: 2/14 evidence lines in window
           apps/api/src/better_resume/http/interview.py:76-76: 2/14 evidence lines in window

   verifiable: 121  partial: 1  unverifiable: 0
   AUDIT_EXIT=1
   STRICT: 1 claim(s) cite a place their own evidence block does not  corroborate (usually line drift). Re-anchor the citation or refresh the evidence.
   ```

   改动前基线（把 `restore_service.py` 临时换成 `git show HEAD` 版本再跑同一支门禁，随后按 md5 校验换回）：`verifiable: 122  partial: 0  unverifiable: 0`。所以这一个 partial 由本票引入，不是存量红。

   ```bash
   cd '/root/better resume/apps/api'
   f=src/better_resume/interview_engine/restore_service.py
   git show HEAD:"apps/api/$f" > /tmp/t19-orig-restore.py
   cp /tmp/t19-orig-restore.py "$f"     # 临时换成 HEAD 版本
   cd '/root/better resume'
   apps/api/.venv/bin/python scripts/verify_audit_evidence.py --strict | tail -2
   cp /tmp/t19-new-restore.py '/root/better resume/apps/api/src/better_resume/interview_engine/restore_service.py'
   md5sum /tmp/t19-new-restore.py '/root/better resume/apps/api/src/better_resume/interview_engine/restore_service.py'
   ```

   ```text
   verifiable: 122  partial: 0  unverifiable: 0
   31a18119bd693fb5b2f060628d4cc866  /tmp/t19-new-restore.py
   31a18119bd693fb5b2f060628d4cc866  /root/better resume/apps/api/src/better_resume/interview_engine/restore_service.py
   ```

   重锚属 `docs/audit/units/*.json`（本票唯一写入路径之外，T22 是专门的重锚票），**没有动它**。T22 需要的最小改动：把 IE-10 的 `where` 里 `restore_service.py:153-156` 换成新的构造段 `restore_service.py:156-162`，并把 evidence 摘录的 `153: return await FlowStateStore(db).initialize(` / `156: max_follow_up=2,` 换成该段现值（`156: return FlowState(` … `162: max_follow_up=2,`）。

2. **行为面收窄，本票没补修复路径**：丢失 `interview_flow_state` 行的会话不再被 restore 自动修好；下一次答题走 `FlowStateStore.require` 会抛 `FlowStateMissing`（`grep -rn "FlowStateMissing" apps/api/src` 只命中 errors/flow_store/`__init__`，HTTP 面无映射、测试面无用例）。票面口径选的是「派生态只读」，这是有意的行为收窄；要不要另立一张票给丢失行一条显式修复路径，未定。
3. **没跑**：`bash scripts/verify.sh --layer all` / `--layer coverage` / `--layer scripts`、compose 与真机演练、前端与契约三件套（本票没动 REST 模型与前端）。
4. **并发写面**：工作区里另有 T13 等票的未提交改动（`question_service.py`、`hot_state.py`、`http/interview.py` 等）。本票落盘只有两个文件：`restore_service.py` 与 `test_restore_report.py`。
5. **红演示不重跑**：红输出取自改动前的唯一一次运行（`/tmp/t19-red.xml`），没有事后补录。
6. 隔离库 `br_t19_verify` 的建法与 drop 原文见本文件末尾；跑完已 drop。

## 隔离库（br_t19_verify）

上述读数一律在这一支隔离库上取（P15-1 口径）；开跑前创建、收工 drop：

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
    await conn.execute("DROP DATABASE IF EXISTS br_t19_verify")
    await conn.execute("CREATE DATABASE br_t19_verify")
    await conn.close()

asyncio.run(main())
PY
```

```text
br_t19_verify ready
```

收工 drop 的原始输出：

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
    await conn.execute("DROP DATABASE br_t19_verify")
    rows = await conn.fetch("select datname from pg_database order by datname")
    print("dropped; databases now:", [r["datname"] for r in rows])
    await conn.close()

asyncio.run(main())
PY
```

```text
dropped; databases now: ['better_resume', 'better_resume_demo', 'postgres', 'template0', 'template1']
```
