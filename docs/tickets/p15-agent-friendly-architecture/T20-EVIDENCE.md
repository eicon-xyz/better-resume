# T20 证据：build_for_model 收进工厂协议（LG-06 收尾）

## 意图复述

- 我理解这票解决什么：T12 已把配置判断收成一个协议钩子（`config_status`），但工厂协议里仍缺模型选择钩子——`SceneResolver.resolve_model` 用 `getattr(factory, "build_for_model", None)` 按私约取用，工厂缺这个方法时被静默翻译成「this build has no openai-compatible provider」，读协议的工厂作者无从知道这条契约存在（LG-06 的 information leakage 半边）。
- 我怎么做，到文件粒度：改 `apps/api/src/better_resume/llm_gateway/resolver.py`（`GatewayFactory` 协议补 `build_for_model` 成员并写清每个钩子的前置条件/缺省语义；`resolve_model` 直接调协议成员，删掉 getattr 兜底），在 `apps/api/tests/llm_gateway/test_scene_resolver.py` 先写「缺 `build_for_model` 的工厂必须响亮失败」的失败用例演示红，再改实现转绿；最后刷新 `docs/audit/units/llm_gateway.json` 的 LG-06（where/evidence 重锚 + why 刷成当前形态 + `fix_record`）。
- 我不做什么：不改场景绑定语义与 HTTP 面（`SceneView`/PUT /scenes/ 响应字段不动）、不动其他 units 条目、不引依赖、不做兼容 shim（协议违约以 AttributeError 响亮失败，与 T12 同口径）、不动 p14 在飞改动、不 commit/push/开 PR。

## 红-绿（先按票演示红）

红用的坏输入 = 改动前 `resolve_model` 的私约形态：协议只声明 `config_status` / `build`，模型选择钩子按 `getattr(factory, "build_for_model", None)` 动态取用，取不到就把错误翻译成「this build has no openai-compatible provider」。用例注册一个只实现前两个钩子的工厂，断言必须响亮失败（AttributeError 且点名 `build_for_model`）。

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t20_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t20-red.xml
uv run pytest -q tests/llm_gateway/test_scene_resolver.py \
  -k 'without_model_selection or goes_through_the_factory_protocol' --junitxml=/tmp/t20-red.xml; echo "EXIT=$?"
```

原始输出（2026-10-17 13:2x，实现改动前）：

```text
>           await resolver.resolve_model("deepseek-flash")

tests/llm_gateway/test_scene_resolver.py:112:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    async def resolve_model(self, model_ref: str | None) -> LlmGateway:
        """Explicit model_ref override (chat picker); bypasses scene bindings on purpose."""
        factory = self._factories.get(AdapterKind.OPENAI_COMPAT)
        builder = getattr(factory, "build_for_model", None)
        if builder is None:
>           raise LlmConfigError("this build has no openai-compatible provider")
E           better_resume.llm_gateway.errors.LlmConfigError: this build has no openai-compatible provider

src/better_resume/llm_gateway/resolver.py:182: LlmConfigError
...
=========================== short test summary info ============================
FAILED tests/llm_gateway/test_scene_resolver.py::test_a_factory_without_model_selection_fails_loudly
EXIT=1
```

同一支命令在隔离库 `br_t20_verify`（建库命令见 §4）上转绿：

```bash
uv run pytest -q tests/llm_gateway/test_scene_resolver.py \
  -k 'without_model_selection or goes_through_the_factory_protocol' --junitxml=/tmp/t20-green-slice.xml; echo "EXIT=$?"
```

```text
EXIT=0
{'tests': 2, 'failures': 0, 'errors': 0, 'skipped': 0}
PIN test_a_factory_without_model_selection_fails_loudly
PIN test_model_selection_goes_through_the_factory_protocol
```

## 验收命令与原始输出

### 1. `build_for_model` 进 Protocol，缺方法响亮失败

```bash
cd '/root/better resume'
grep -n 'build_for_model\|class GatewayFactory\|async def resolve_model' \
  apps/api/src/better_resume/llm_gateway/resolver.py
```

```text
65:class GatewayFactory(Protocol):
70:    the binding cannot be honoured. `build_for_model` is the explicit model-ref path (the
80:    async def build_for_model(self, model_ref: str | None) -> LlmGateway: ...
107:        return await self.build_for_model(binding.target_ref)
109:    async def build_for_model(self, model_ref: str | None) -> LlmGateway:
187:    async def resolve_model(self, model_ref: str | None) -> LlmGateway:
196:        return await factory.build_for_model(model_ref)
```

协议块（`resolver.py:64-80`）声明了三个钩子并写明各自的前置条件与缺省语义；`resolve_model`（`resolver.py:187-196`）直接调用协议成员，没有兜底分支。缺方法时的真实失败形态：

```bash
cd '/root/better resume/apps/api'
uv run python - <<'PY'
import asyncio

from better_resume.llm_gateway import AdapterKind, SceneResolver


class MinimalFactory:
    """Only the two binding hooks of the protocol."""

    async def config_status(self, binding):
        raise AssertionError("not reached")

    async def build(self, binding):
        raise AssertionError("not reached")


resolver = SceneResolver(None, factories={AdapterKind.OPENAI_COMPAT: MinimalFactory()})
try:
    asyncio.run(resolver.resolve_model("deepseek-flash"))
except AttributeError as exc:
    print(f"{type(exc).__name__}: {exc}")
PY
```

```text
AttributeError: 'MinimalFactory' object has no attribute 'build_for_model'
```

### 2. `grep -n "getattr"` 私约清零（剩余命中逐条注明）

```bash
cd '/root/better resume'
grep -rn 'getattr' apps/api/src/better_resume/llm_gateway --include='*.py'
```

```text
apps/api/src/better_resume/llm_gateway/scene_mapping.py:113:        if getattr(message, "role", None) != "user":
```

- `scene_mapping.py:113` —— 对 `inspect_for_injection(messages: list[Any])` 的输入做 `role` 的防御读，不是工厂/协议私约，与 `build_for_model` 无关；本票不动它。

协议取用点已经归零：`resolver.py` 里不再有 `getattr`。

### 3. LG-06：where/evidence 重锚、why 刷成当前形态、记 `fix_record`

```bash
cd '/root/better resume'
apps/api/.venv/bin/python - <<'PY'
import json

data = json.load(open("docs/audit/units/llm_gateway.json", encoding="utf-8"))
issue = next(i for i in data["issues"] if i["id"] == "LG-06")
print("LG-06 keys:", ",".join(issue))
print("where:", json.dumps(issue["where"], ensure_ascii=False))
print("fix_record.status:", issue["fix_record"]["status"])
print("fix_record.title:", issue["fix_record"]["title"])
print("fix_record.files:", json.dumps(issue["fix_record"]["files"], ensure_ascii=False))
print("issue count:", len(data["issues"]))
PY
```

```text
LG-06 keys: id,dim,signals,severity,title,where,evidence,why,fix,fix_record
where: ["apps/api/src/better_resume/llm_gateway/resolver.py:64-80", "apps/api/src/better_resume/llm_gateway/resolver.py:106-113", "apps/api/src/better_resume/llm_gateway/resolver.py:187-196"]
fix_record.status: fixed
fix_record.title: build_for_model 是工厂协议的成员：resolver 直接调用，缺实现以 AttributeError 响亮失败
fix_record.files: ["apps/api/src/better_resume/llm_gateway/resolver.py", "apps/api/tests/llm_gateway/test_scene_resolver.py"]
issue count: 13
```

`fix_record.evidence` 指向 §1 的红→绿用例与 AttributeError 实测；`fix_record.unverified` 写明「非 openai_compat 工厂不实现该钩子」这条约束没有用例钉住。LG-06 的 `title`/`fix` 保持原文（票面只授权 why 刷新与 fix_record）；其余 12 条 issue 未动。

### 4. `--strict` 退出 0、定向 pytest 绿、隔离库权威全量

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run --project apps/api python scripts/verify_audit_evidence.py --strict; echo "AUDIT_EXIT=$?"
uv run --project apps/api python scripts/verify_audit_evidence.py --structural; echo "STRUCT_EXIT=$?"
```

```text
verifiable: 122  partial: 0  unverifiable: 0
AUDIT_EXIT=0
structure ok: 10 units / 122 issues / 340 citations
STRUCT_EXIT=0
```

隔离库自建（fixture 自己 `alembic upgrade head`；全部读数取完即 drop）：

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
    await conn.execute("DROP DATABASE IF EXISTS br_t20_verify WITH (FORCE)")
    await conn.execute("CREATE DATABASE br_t20_verify")
    await conn.close()

asyncio.run(main())
PY
```

```text
databases: ['br_t20_verify']
```

定向集（`BR_DATABASE_URL=...:5433/br_t20_verify`）：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t20_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t20-target2.xml
uv run pytest -q tests/llm_gateway tests/test_scene_routing.py tests/test_models_api.py tests/test_verify_script.py \
  --junitxml=/tmp/t20-target2.xml; echo "EXIT=$?"
```

```text
EXIT=0
{'tests': 149, 'failures': 0, 'errors': 0, 'skipped': 0}
```

权威全量（同一支命令、只换 junitxml 路径，隔离库上串行跑）：

```bash
cd '/root/better resume/apps/api'
rm -f /tmp/t20-full.xml
uv run pytest -q --junitxml=/tmp/t20-full.xml; echo "FULL_EXIT=$?"
```

```text
2026-10-17T13:27:10+08:00
FULL_EXIT=0
2026-10-17T13:28:46+08:00
{'tests': 1011, 'failures': 0, 'errors': 0, 'skipped': 0, 'time': '90.449'}
```

跑完 drop，无残留库：

```text
br_* databases left: []
```

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
| `build_for_model` 作为 `GatewayFactory` 的第三个成员声明（与 `config_status`/`build` 并列），不新起第二个「有模型选择能力的工厂」协议 | 票面就是「收进工厂协议」，且协议 docstring 明确写了缺省语义：该钩子由按模型名选择的适配器提供，resolver 直接调用，缺实现以 AttributeError 点名——新工厂作者读一份协议就看到全部钩子（这正是 LG-06 的 information leakage） | 没有为 Xingyun/DashScope 两个工厂补一个语义空洞的 `build_for_model`（它们由 flow_id / app_id 定位，没有模型维；`resolve_model` 只查 `AdapterKind.OPENAI_COMPAT`） |
| 缺方法时的失败保持 AttributeError（`factory.build_for_model(...)` 直接调用），只保留「本构建没注册该 adapter kind」这一种 `LlmConfigError`（工厂为 None） | 与 T12 同口径：协议违约响亮失败、不做兼容 shim；AttributeError 的消息本身就点名缺失钩子，比兜底文案可执行 | 没写 `isinstance(factory, ...)`／`hasattr` 守卫，也没把 AttributeError 包成 LlmConfigError |
| 红用例（`test_a_factory_without_model_selection_fails_loudly`）写在 `apps/api/tests/llm_gateway/test_scene_resolver.py`——即 llm_gateway.json 的 scope 内、本票点名的缝 | 验收口径 1 要求红演示用例，而测试不能写进 `src/`；该文件是 resolver 自己的用例文件，属 llm_gateway 单元的声明面 | 没有新开测试文件、没有动其他模块的测试 |
| 同时补一条正向用例 `test_model_selection_goes_through_the_factory_protocol`（显式 model_ref 交给工厂的 `build_for_model`，不经绑定） | 删掉 getattr 兜底后，这条通路此前没有任何用例钉住；两条断言合起来覆盖「缺钩子响亮失败 / 有钩子被调用」 | 没有为 picker 的 503 映射另加用例（HTTP 面不在本票红线的改动范围） |
| LG-06 的 where/evidence 一并重锚到当前行号（改动后 resolver 行号下移），`title`/`fix` 保持原文 | AGENTS：改过被引用的文件后引证要重锚，否则逐字级门槛会红；票面只授权 why 刷新与 fix_record，不动 issue 描述 | 没有改 LG-06 的 title/fix，没有给其他条目记 fix_record |
| 因本次代码移位，连带重锚了 LG-10（`resolver.py:139-144`、`test_scene_resolver.py:175-184`）与 LG-12（`resolver.py:259-262`）的 where 行号 | 这两条被 `--strict` 判 PART（窗口落到已移位的代码上），不重锚则验收口径 4 无法退出 0；只改行号，不改结论 | 没有动这两条的 evidence/why/fix，也没给它们记 fix_record；没有顺带重锚 LG-07/LG-09 的 resolver 引证（见未验证项） |

## 未验证项（诚实清单）

1. **LG-07 / LG-09 的 resolver 引证随本次移位变旧**：`resolver.py:91-106`（LG-07）与 `resolver.py:236-241`（LG-09）指向的代码段已整体下移，当前仍被 `--strict` 判绿——靠的是 P15-7 记录过的弱匹配（短摘录如 `)`）。按本票红线「不动其他 units 条目」未重锚，留给出票方裁决。
2. **非 openai_compat 工厂不实现 `build_for_model` 这条约束没有用例钉住**：它由 `resolve_model` 只查 `AdapterKind.OPENAI_COMPAT` 保证；若将来有第二个按模型名选择的 adapter kind，需要新的用例（已写进 LG-06 的 `fix_record.unverified`）。
3. 未跑真机 / HTTP 端到端：`/scenes` 与模型 picker 的 503 文案未做浏览器手测；本票未改 HTTP 面与 REST 模型，故未跑契约三件套。
4. 未跑前端测试与 `pnpm`：本票未动 web 与 openapi。
5. 全量读数只在本机隔离库上取过一次（1011/0/0/0）；并行票的共享库读数未取（P15-1：共享库读数不可信，一律自建隔离库）。

## 附加读数：`scripts` 层（旁证，非本票验收项）

`bash scripts/verify.sh --layer scripts` 的 12 条命令里 11 条 EXIT=0，唯一红在引证门禁：

```text
[6/12] find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
FAIL docs/tickets/p15-agent-friendly-architecture/T17-audit-reanchor.md:29 引证「resolver.py:999-1005」：行号 999-1005 越界（apps/api/src/better_resume/llm_gateway/resolver.py 共 265 行）
引证 106（直配 69，短名兜底 36）解析成功 105 失败 1
```

- 归因：该引证在 T17 票据的追记里（变异演示故意写一个越界行号），与本次改动无关——本票开工时读到的 `resolver.py` 是 252 行，999-1005 当时同样越界；该文件在 `docs/tickets/` 下，属本票写入面之外，未动。
- 其余 11 条逐条 EXIT=0：`verify_secrets.sh`（selftest + 0 hits / 622 files）、`verify_docs_hygiene.sh`（selftest 11/11，扫描 514 文件 0 命中）、`verify_citations.sh --selftest`（6/6）、`ticket_frontier.sh`（selftest 8/8，p15 目录 20 张票结构通过）、scripts 子集 pytest（101/0/0/0）、`bash -n`（全部 shell）、`check_scripts.py`（24 个脚本）、`verify_audit_evidence.py --structural`（10 units / 122 issues / 340 citations）。
