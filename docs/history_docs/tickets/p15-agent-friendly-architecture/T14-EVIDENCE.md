# T14 证据：适配器协议契约测试

## 意图复述

- 我理解这票解决什么：P11 那三条「库与协议的默认值没显式化」的坑（`wait()` 提前返回、成功路径不明示 `close(1000)`、连接参数吃 `websockets` 默认值）目前只靠「新 adapter 先跑一次真实链路」的人肉纪律；票要把它们变成一套会真判定的契约测试，而且套件自己必须先被坏 fake 证伪（每条契约至少一个故意违规的假适配器要被判红）。
- 我怎么做，到文件粒度：新增 `apps/api/tests/media/test_adapter_contract.py`（三个契约检查函数 + 拿真实适配器当主体的用例 + 每条契约一个坏 fake 的自证用例）；为过「成功路径显式 `close(1000)`」契约，对 `apps/api/src/better_resume/media/adapters/paraformer_rt.py` 的 `_run_session` 收尾做最小修正，并让 `apps/api/tests/media/test_paraformer_rt.py` 里的假供应商 socket 接受并记录 `close(code)`。
- 我不做什么：不改适配器对外行为、不改协议 models/settings、不引依赖；xunfei AST 适配器没有注入缝（要真凭据 + 真网络）按票面跳过并在套件里写明；不动工作区里 p14 在飞的未提交改动与 p15 以外的 docs；不 commit / push / 开 PR。

## 红-绿（先按票演示红）

### 红 1：坏 fake 必须被判红（本票核心自证，原样可复跑）

不看真实适配器，直接把三个契约检查函数套在三个故意违规的假适配器上。这条命令现在跑也是同样三行红（不依赖工作区处于修前还是修后）：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run python - <<PY
import asyncio
import websockets
from tests.media.test_adapter_contract import (
    ConnectSpy, EarlyWaitChannel, SilentCloseChannel, _open_with_library_defaults,
    assert_connect_params_explicit, assert_success_closes_with_1000,
    assert_wait_blocks_until_stop,
)

async def main() -> None:
    silent = SilentCloseChannel()
    spy = ConnectSpy()
    websockets.connect = spy
    cases = [
        ("契约1 wait() 在 stop() 前返回", assert_wait_blocks_until_stop, EarlyWaitChannel()),
        ("契约2 成功路径关闭码吃库默认值",
         lambda c: assert_success_closes_with_1000(c, c.transport), silent),
        ("契约3 连接参数吃库默认值",
         lambda c: assert_connect_params_explicit(_open_with_library_defaults, spy), None),
    ]
    for name, run, subject in cases:
        try:
            await (run(None) if subject is None else run(subject))
        except AssertionError as exc:
            print("坏 fake 判红 OK [" + name + "] -> AssertionError: " + str(exc).splitlines()[0])
        else:
            print("坏 fake 漏判 FAIL [" + name + "] -> 契约检查放行了违规实现")

asyncio.run(main())
PY
```

原始输出（2026-10-17）：

```text
坏 fake 判红 OK [契约1 wait() 在 stop() 前返回] -> AssertionError: wait() returned before stop(): the transcription WebSocket would close the client socket while the vendor tail is still coming (P20)
坏 fake 判红 OK [契约2 成功路径关闭码吃库默认值] -> AssertionError: a successful WS run must close the vendor socket with an explicit 1000 (got None): leaving the code to the library default hides a stalled close from both ends (P21)
坏 fake 判红 OK [契约3 连接参数吃库默认值] -> AssertionError: open_timeout must be the caller value, got None
```

### 红 2：修前真实适配器在契约 2 上判红

修 `paraformer_rt.py` 之前，契约套件对真实 paraformer-rt 跑出 1 红（它当时 `await connection.close()`，关闭码留给库默认值）：

```text
>       assert code == 1000, (
            f"a successful WS run must close the vendor socket with an explicit 1000 (got {code!r}): "
            "leaving the code to the library default hides a stalled close from both ends (P21)"
        )
E       AssertionError: a successful WS run must close the vendor socket with an explicit 1000 (got None): leaving the code to the library default hides a stalled close from both ends (P21)
E       assert None == 1000
tests/media/test_adapter_contract.py:93: AssertionError
FAILED tests/media/test_adapter_contract.py::test_realtime_asr_closes_the_vendor_socket_with_1000
EXIT=1
junitxml tests=8 failures=1 errors=0 skipped=0
```

要复现这次红（临时去掉那一行显式关闭码，跑完还原）：

```bash
cd '/root/better resume'
git stash push -- apps/api/src/better_resume/media/adapters/paraformer_rt.py
cd '/root/better resume/apps/api'
uv run pytest tests/media/test_adapter_contract.py -q --junitxml=/tmp/t14-red.xml; echo "EXIT=$?"
cd '/root/better resume' && git stash pop
```

## 验收命令与原始输出

### 1. 契约套件对真实适配器全绿（8 例）

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest tests/media/test_adapter_contract.py -o addopts="" -v --no-header --tb=no -p no:warnings
```

```text
tests/media/test_adapter_contract.py::test_scripted_channel_wait_blocks_until_stop PASSED [ 12%]
tests/media/test_adapter_contract.py::test_batch_asr_wait_blocks_until_stop PASSED [ 25%]
tests/media/test_adapter_contract.py::test_realtime_asr_wait_blocks_until_stop PASSED [ 37%]
tests/media/test_adapter_contract.py::test_contract_one_reddens_a_channel_that_returns_from_wait_early PASSED [ 50%]
tests/media/test_adapter_contract.py::test_realtime_asr_closes_the_vendor_socket_with_1000 PASSED [ 62%]
tests/media/test_adapter_contract.py::test_contract_two_reddens_a_socket_closed_with_the_library_default PASSED [ 75%]
tests/media/test_adapter_contract.py::test_real_ws_opener_passes_explicit_connection_params PASSED [ 87%]
tests/media/test_adapter_contract.py::test_contract_three_reddens_an_opener_using_library_defaults PASSED [100%]
============================== 8 passed in 0.07s ===============================
```

同一套件连跑 5 次（`--junitxml` 读数，不抄固定值）：

```text
run1 exit=0 tests=8 failures=0 errors=0
run2 exit=0 tests=8 failures=0 errors=0
run3 exit=0 tests=8 failures=0 errors=0
run4 exit=0 tests=8 failures=0 errors=0
run5 exit=0 tests=8 failures=0 errors=0
```

### 2. 票面点名的三条断言，落在哪个主体上

| 契约 | 检查函数 | 绿的真实主体 | 判红的坏 fake | 跳过并写明 |
| --- | --- | --- | --- | --- |
| 1 `wait()` 在 `stop()` 之前不得返回 | `assert_wait_blocks_until_stop` | `ScriptedTranscriptionChannel`、`QwenAsrFlashAdapter`（P20 的回归面）、`ParaformerRealtimeAdapter` | `EarlyWaitChannel`（`wait()` 立刻返回） | — |
| 2 成功路径显式 `close(1000)` | `assert_success_closes_with_1000` | `ParaformerRealtimeAdapter`（经它的 `connect=` 缝 + 假供应商 socket） | `SilentCloseChannel`（socket 不带码关闭） | xunfei AST：接收循环直接绑定 `websockets.connect`，没有注入缝，跑契约要真凭据 + 真网络（套件 docstring 写明） |
| 3 连接参数（open/close 超时、proxy）不得吃库默认值 | `assert_connect_params_explicit` | `paraformer_rt.open_connection`（`websockets.connect` 换记录替身） | `_open_with_library_defaults`（只传头） | 同上；scripted 无传输层，契约 2/3 对它不适用 |

### 3. media 目录全绿 + 全量 pytest 读数

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest tests/media -q -p no:warnings --junitxml=/tmp/t14-media.xml
```

```text
============================== 73 passed in 1.84s ==============================
media junitxml tests=73 failures=0 errors=0 skipped=0
```

票面点名的全量命令（原样）：

```bash
cd apps/api
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv' \
  BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' \
  BR_REDIS_URL='redis://127.0.0.1:6379/0' \
  && uv run pytest -q --junitxml=/tmp/t14.xml
```

读数（同一条命令跑两次，都不绿；红灯集合还在变，因为 p14 正在改这些文件）：

```text
第一次：junitxml tests=1009 failures=10 errors=0 skipped=0
  tests/interview_engine/test_restore_report.py 6 例（SessionNotFound / 出题写路径没有失效热层）
  tests/llm_gateway/test_scene_binding_store.py 2 例（llm_scene_bindings 主键重复 / 默认绑定缺失）
  tests/llm_gateway/test_scene_resolver.py 1 例（SceneResolver 没有 bind）
  tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence 1 例
第二次：junitxml tests=1009 failures=4 errors=2 skipped=0
  tests/interview_engine/test_answer_service.py 3 例、tests/interview_engine/test_follow_up_flow.py 2 例、
  tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence 1 例
```

**这 10/6 个红灯没有一个是本票的**，证据三条：

1. 红灯全部落在 `git status` 里 p14 的未提交改动覆盖的模块（`interview_engine/*`、`llm_gateway/*`、`http/interview.py` 及它们的测试文件）；本票改的 `media/` 零红灯，`tests/test_media_ws.py` 也在两次全量里都过。
2. 把本票的两处改动 path-limited stash 掉后，同一批红灯照旧（`junitxml tests=57 failures=9 errors=0`，例：`tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`、`test_restore_report` 的一批），跑完 `git stash pop` 已还原（还原后 diff 与备份补丁逐字相同）。
3. 引证那一条的失败明细全部指向 p14 改过的位置（`llm_gateway/resolver.py` 多段、`apps/api/src/better_resume/http/interview.py:491-493 outside 1..490`、`apps/web/src/interview/useInterviewRoom.ts`），media 的引证一条未变：本票在 `paraformer_rt.py` 第 268 行前插入 1 行注释，被引用的 media 行号最大是 248，全部未移位。

这些红灯需要 p14 自己收口（红线禁止本票触碰），本票不代修。

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 契约检查写成三个可复用的断言函数，用例分「真实主体绿」与「坏 fake 红」两组 | 套件自证要求坏 fake 被判红；抽成函数才能让同一个判定同时作用在真实适配器和坏 fake 上，判定逻辑只有一个所有者（P08） | 没抽成生产代码工具或 pytest 插件——目前只有测试用（YAGNI） |
| 契约 1 用 5 次 `await asyncio.sleep(0)` 让提前返回的 fake 暴露，不引入真 sleep 或超时 | 判定不该依赖真实时间（P04）：提前返回的 fake 在第一个调度点就做完，真实通道只会停在事件上 | 没断言 `wait()` 内部实现（如是否用 Event） |
| 契约 2 的观测量是假供应商 socket 收到的关闭码，而不是去读 websockets 内部状态 | 断言走公开行为：适配器唯一能表达「显式 1000」的地方就是传给 `close()` 的入参 | 没断言 `close()` 的调用次数与顺序 |
| paraformer 的假供应商复用 `tests/media/test_paraformer_rt.py` 的 `FakeVendor`（只把它改成接受并记录 `close(code)`），不在契约文件里再写一份 | 两份必须相等的 fake 会漂移，一处真源（P08） | 没把 `FakeVendor` 挪进共享 helpers/conftest——挪动会改到 p14 邻居文件，收益不抵风险 |
| 只改 `paraformer_rt._run_session` 收尾的 `close()` → `close(1000)`；成功与失败路径共用这个收尾 | 一行最小修正；失败路径的 socket 本来就要关，显式码不改变语义 | 没改 xunfei 的 `async with connect(...)`（它连 `close_timeout`/`proxy` 都没显式传，是同一类隐患）——它没有注入缝，改完在本环境无法验证，按票面「无凭据跳过并写明」处理 |
| 契约 3 断言 `proxy` 必须显式 `None`，并把「库默认值」用 `inspect.signature(websockets.connect)` 现取 | 「不得吃库默认值」要真判定；硬抄常量会在库改默认值那天变成假断言 | 没为 websockets < 14 的 `extra_headers` 分支单写用例（只对关键字名做了双拼容错） |
| 契约套件跳过 xunfei AST 适配器并在 docstring 写明 | 它的接收循环直接绑定 `websockets.connect`，没有 `connect=` 注入缝；跑契约要真凭据 + 真网络，本套件不允许有这个前提 | 没给 xunfei 加注入缝——那会改构造签名，属于适配器对外行为 |
| 全量 pytest 未转绿，按原始读数如实记录，不代修 p14 的红灯 | 票面红线「不动 p14 在飞的未提交改动」优先于「全量绿」这条验收；红灯已用基线复现证明与本票无关 | 没碰 `interview_engine` / `llm_gateway` / `http` / `docs/audit` 的任何文件 |

