# T12 证据：配置状态改为同步快照 API（建议 3）

## 意图复述

- 我理解这票解决什么：llm_gateway 的场景配置判断仍是一个「async 布尔」钩子（`_call` 兼容同步/异步、`is_configured` 返回协程），历史 bug（P01/P11：漏 await → 协程恒真 → 守卫被静默跳过）的写法仍能被写出来；票要把它换成一次取回、直接读值的配置状态快照，让「漏 await 判定」在结构上写不出来。
- 我怎么做，到文件粒度：改 `apps/api/src/better_resume/llm_gateway/resolver.py`（GatewayFactory 协议、OpenAiCompatFactory、SceneResolver.resolve/views、删除 `_call` 与模块级 `is_configured`）、`xingyun_factory.py`、`dashscope_app_factory.py`、`__init__.py`；同步改 `apps/api/tests/llm_gateway/test_scene_resolver.py`、`test_xingyun_adapter.py`、`test_dashscope_app_factory.py`、`apps/api/tests/test_scene_routing.py` 里实现该协议的 fake。先写失败用例（旧异步布尔工厂不得被静默接受）演示红，再改实现转绿。
- 我不做什么：不改 HTTP/DB 面与公开场景绑定语义（SceneView/接口字段不变）；不引依赖；不动 p14 在飞的未提交改动、其他 docs；不 commit/push/开 PR；新增第二套配置判断。

## 红-绿（先按票演示红）

红用的坏输入 = 改动前的配置判断缝：`_call` 同时兼容同步/异步工厂，`is_configured` 是 async 布尔；resolver 必须 `await` 才有值，工厂只给一个异步布尔钩子也能进守卫。

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t12-red.xml
uv run pytest -q tests/llm_gateway/test_scene_resolver.py \
  -k 'legacy_async_boolean or config_status_snapshot' --junitxml=/tmp/t12-red.xml; echo "EXIT=$?"
```

原始输出（2026-10-17 12:41，改动前，完整日志 /tmp/t12-red.log）：

```text
EXIT=1
FF                                                                       [100%]
...
        with pytest.raises(AttributeError, match="config_status"):
>           await resolver.resolve(LlmScene.CHAT)
...
E           better_resume.llm_gateway.errors.LlmConfigError: scene 'chat' (xingyun:flow-legacy) is not configured; credentials are missing
...
>       with pytest.raises(LlmConfigError, match="set XINGCHEN_API_KEY"):
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'set XINGCHEN_API_KEY'
E         Actual message: "scene 'chat' (xingyun:flow-snap) is not configured; credentials are missing"
=========================== short test summary info ============================
FAILED tests/llm_gateway/test_scene_resolver.py::test_legacy_async_boolean_is_not_the_seam
FAILED tests/llm_gateway/test_scene_resolver.py::test_config_status_snapshot_carries_the_missing_credential
```

两条红用例钉的就是历史形态：旧异步布尔钩子仍被 `_call` 兼容（只给 `async def is_configured` 的工厂也能走到守卫），且「缺哪个环境变量」要第二次 `credential_hint()` 调用才拿得到。

改后，同两条用例（连同 llm_gateway 全域、场景路由、模型面）在隔离库上（库的建法见 §4，同一支 pytest 命令）：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t12_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q tests/llm_gateway tests/test_scene_routing.py tests/test_models_api.py \
  --junitxml=/tmp/t12-target3.xml; echo "EXIT=$?"
```

```text
EXIT=0
{'tests': 120, 'failures': 0, 'errors': 0, 'skipped': 0}
PIN test_legacy_async_boolean_is_not_the_seam
PIN test_config_status_snapshot_carries_the_missing_credential
```

## 验收命令与原始输出

### 1. 配置状态判断在调用面上是同步值，不再有「await 才有值」的布尔

```bash
cd '/root/better resume'
grep -rn 'config_status' apps/api/src
```

```text
apps/api/src/better_resume/llm_gateway/__init__.py:38:    ConfigStatus,
apps/api/src/better_resume/llm_gateway/__init__.py:53:    "ConfigStatus",
apps/api/src/better_resume/llm_gateway/resolver.py:45:class ConfigStatus:
apps/api/src/better_resume/llm_gateway/resolver.py:64:    async def config_status(self, binding: SceneBinding) -> ConfigStatus: ...
apps/api/src/better_resume/llm_gateway/resolver.py:82:    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
apps/api/src/better_resume/llm_gateway/resolver.py:87:            return ConfigStatus(configured=False)
apps/api/src/better_resume/llm_gateway/resolver.py:89:            return ConfigStatus(configured=True)
apps/api/src/better_resume/llm_gateway/resolver.py:90:        return ConfigStatus(configured=False, missing=spec.api_key_env)
apps/api/src/better_resume/llm_gateway/resolver.py:191:        status = await factory.config_status(binding)
apps/api/src/better_resume/llm_gateway/resolver.py:233:                await factory.config_status(binding)
apps/api/src/better_resume/llm_gateway/resolver.py:235:                else ConfigStatus(configured=False)
apps/api/src/better_resume/llm_gateway/dashscope_app_factory.py:14:from .resolver import ConfigStatus
apps/api/src/better_resume/llm_gateway/dashscope_app_factory.py:26:    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
apps/api/src/better_resume/llm_gateway/xingyun_factory.py:12:from .resolver import ConfigStatus
apps/api/src/better_resume/llm_gateway/xingyun_factory.py:31:    async def config_status(self, binding: SceneBinding) -> ConfigStatus:
```

两处 `await` 等来的都是 `ConfigStatus` 值对象，判定分别是 `if not status.configured`（resolver.py:191-192）与 `configured=status.configured`（resolver.py:239）；值对象带 `__bool__`，`if not status` 读的也是同一个值（未配置时为假）。旧的「await 一个布尔」写法在调用面上已不存在。

### 2. `grep -rn "is_configured" apps/api/src` 剩余命中逐条说明

```bash
cd '/root/better resume'
grep -rn 'is_configured' apps/api/src
```

```text
apps/api/src/better_resume/llm_gateway/registry.py:67:    def is_configured(self, spec: ModelSpec) -> bool:
apps/api/src/better_resume/llm_gateway/resolver.py:88:        if self._registry.is_configured(spec):
apps/api/src/better_resume/http/models.py:26:            configured=registry.is_configured(spec),
```

- registry.py:67 —— 本来就是同步布尔快照（查 env 里有没有 key），无协程，保留；
- resolver.py:88 —— 同步读上面那份快照；
- http/models.py:26 —— 同步取值填 `configured` 响应字段。

场景工厂那套 async 布尔钩子（resolver 模块级 `is_configured` / `credential_hint` 与三个工厂的同名方法）已删除：协议方法统一为 `async config_status(binding) -> ConfigStatus`，一次返回「能不能跑 + 缺哪个变量」。

### 3. 票面全量命令（共享库）——读数被并行票污染，不作数

```bash
cd apps/api && export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv' \
BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' \
BR_REDIS_URL='redis://127.0.0.1:6379/0' && uv run pytest -q --junitxml=/tmp/t12.xml
```

同一命令两次读数：

- 2026-10-17 12:50 —— `{'tests': 1009, 'failures': 2, 'errors': 0, 'skipped': 0}`，两条失败：`tests/test_distributed_lock.py::test_lease_is_renewed_while_held`（时序，单跑绿）、`tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`；
- 2026-10-17 12:52（/tmp/t12-full.log 现存这一份）—— `{'tests': 1009, 'failures': 6, 'errors': 5, 'skipped': 0}`，失败形态是共享库被另一个进程 TRUNCATE 之后的 `SessionNotFound` / 外键冲突（下面明细按同一支命令的 --junitxml 读数打印）：

```text
ERROR tests/interview_engine/test_follow_up_flow.py::test_follow_up_inherits_the_main_question_category
BAD tests.interview_engine.test_question_service test_focus_points_are_stored | better_resume.interview_engine.errors.SessionNotFound: interview session b5748ea5-a4bb-45db-b18b-c8e3a301977f not found
BAD tests.test_job_worker_api test_worker_fills_the_summary_of_the_frozen_report | AssertionError: {"detail":"interview session 8f6e4f31-db90-472e-b7d9-81b50ecba99d not found"}
```

两次失败集不同即可判定读数不可信；同一时间窗 `ps` 实测到并行票的全量 pytest 进程（T13 `/tmp/t13-green2.xml`、T14 `/tmp/t14-b.xml`，日志文件见 /tmp）：

```text
$ ps -eo pid,etimes,cmd | grep -E '\.venv/bin/pytest'
58877      47 uv run pytest -q --junitxml=/tmp/t14-b.xml
56267       9 uv run pytest -q ... --junitxml=/tmp/t13-green2.xml
```

### 4. 隔离库复跑（同一支命令，只换 BR_DATABASE_URL 的库名）

先建空库 `br_t12_verify`（测试 fixture 自己 `alembic upgrade head`；跑完 drop）：

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
    await conn.execute("CREATE DATABASE br_t12_verify")
    await conn.close()

asyncio.run(main())
PY
```

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t12_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t12-iso.xml
uv run pytest -q --junitxml=/tmp/t12-iso.xml; echo "EXIT=$?"
```

```text
EXIT=1
FAILED tests/test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence
{'tests': 1009, 'failures': 1, 'errors': 0, 'skipped': 0}
```

唯一失败是 docs 审计逐字级门禁（仓级 gating，不属本票写入面）：

```bash
cd '/root/better resume'
apps/api/.venv/bin/python scripts/verify_audit_evidence.py --strict; echo "AUDIT_EXIT=$?"
```

```text
PART  [llm_gateway] LG-07: 「凭证是否齐备 / 缺哪个环境变量」在三个工厂里各写一遍，表达方式还各不相同
        apps/api/src/better_resume/llm_gateway/resolver.py:91-106: 1/17 evidence lines in window
STRUCT http/http-13: apps/api/src/better_resume/http/interview.py:491-493 outside 1..490

1 structural problem(s) in 10 unit(s)
AUDIT_EXIT=1
```

归因：`http/interview.py` 现 490 行、正被并行票改动（`git diff --stat` 显示 `8 insertions(+), 17 deletions(-)`），审计单元引用的 491-493 已越界——这是外部票造成的结构级红；同时本票（与并行票）移动了 resolver.py 行号，LG-06/07/10/12 的引证需重锚。两者都落在 `docs/audit/units/*.json`，属 docs 写路径（本票红线：只写 `apps/api/` + 本证据文件），未动。

### 5. ruff（本票改动面）

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run ruff check src/better_resume/llm_gateway tests/llm_gateway tests/test_scene_routing.py; echo "CHECK_EXIT=$?"
uv run ruff format --check src/better_resume/llm_gateway tests/llm_gateway tests/test_scene_routing.py; echo "FORMAT_EXIT=$?"
```

```text
All checks passed!
CHECK_EXIT=0
32 files already formatted
FORMAT_EXIT=0
```

## 实现决定交代

| spec 未覆盖我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 配置状态做成值对象 `ConfigStatus(configured, missing)`，协议钩子由 `is_configured` + `credential_hint` 两个合并成一个 `async config_status(binding)`，并给值对象加 `__bool__` | 一次 probe 同时回答「能不能跑」和「缺哪个变量」，删掉第二个钩子；`__bool__` 让 `if not status` 这种写法也读同一个值（未配置为假），历史 bug 的「协程恒真」在值对象上没有落点 | 没把工厂方法改成同步：registry 查库天然 async，同步化需要在 resolver 里另存快照并引入缓存时点语义（属 T13 范围），会改变配置判断的时机 |
| 删掉 `_call` 的「同步/异步都接受」分支，旧异步布尔工厂不再被兼容：只给 `async is_configured` 的工厂在 resolve 时以 `AttributeError: ... config_status` 失败，并用一条红→绿用例钉住 | 兼容层正是 P01/P11 里「错误写法还能跑」的入口；接口收窄成一种签名，调用方少学一样东西 | 没给旧工厂做 shim / 迁移告警 / 兼容回退 |
| resolver 判定统一写成 `status = await factory.config_status(binding)` 后 `if not status.configured`；views 里工厂缺失时用 `ConfigStatus(configured=False)` 占位 | 判断读值不读协程；工厂缺失（adapter 本进程不提供）与未配置同为「跑不了」，与原 `bool(factory) and ...` 语义一致 | 没给 `SceneResolver` 新增同步公开方法（如 `config_status(scene)`）——那会把配置判断的时点绑到绑定缓存上 |
| 三个工厂的 `config_status` 都声明为 `async`（Xingyun/DashScope 内其实无 await） | 协议只有一个签名，调用方不用学第二套同步/异步分支 | 没为纯同步工厂保留同步重载 |
| 未改 503 文案结构与 `SceneView` / HTTP 响应字段 | 行为只收窄到「判断真的会执行」；公开场景绑定语义不变 | 没动 http 层、没动 `SceneViewResponse` 与前端契约 |
| 没给 `ConfigStatus` 加冻结校验/工厂注册表校验 | 值与协议都在同一模块，单测已覆盖未配置/缺变量两条路径 | 没引依赖、没加第二套配置判断 |

## 未验证项（诚实清单）

1. 票面全量命令在**共享库**上两次读数都被并行票污染（失败集不同，12:50 为 2 失败、12:52 为 6 失败 5 错误）；可信读数是隔离库的 `1009 tests / 1 failure / 0 errors / 0 skipped`，唯一失败是 docs 审计逐字级门禁，其结构级红来自并行票改动的 `http/interview.py`（490 行 vs 引证 491-493），非本票改动。
2. 未跑真机 / HTTP 端到端（未启服务）；`/api/v1/scenes` 的 `configured` 行为由单测覆盖，未做浏览器手测。
3. 未跑前端测试与契约三件套：本票未改 REST 模型与 `openapi.json`（`SceneViewResponse` 字段未变），故不涉及。
4. `skills/modules/llm_gateway/SKILL.md` 仍写着「`is_configured` 是 async」——该文件不在本票写入路径（apps/api 之外），未改，需要文档侧票更新。
5. `docs/audit/units/llm_gateway.json` 的 LG-06/07/10/12 引证行号因本票与并行票移动而失效，未重锚（docs 写路径），需要文档侧票处理。
