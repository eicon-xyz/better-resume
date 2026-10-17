# T22 证据包（收口重锚与渲染产物重建）

## 意图复述
- 全代码票落定后，重锚 `docs/audit/units/*.json` 里因代码移位而失效的引证（含 T20 波及的 LG-07/LG-09），把 `verify_audit_evidence.py --strict` 从 partial 2 / unverifiable 2 转到 0/0，不改审计结论、不改 issue 描述。
- 唯一写入路径是 `docs/audit/units/*.json` 与由生成脚本重建的 `docs/audit/MODULE-AUDIT.html`；不改代码、不 commit/push/开 PR、不动 p14 在飞改动。
- 交付 T22-EVIDENCE.md：原始读数可复跑、≥30 条引证语义抽样判词（含 P15-7 点名的 LG-09 弱匹配窗口）、隔离库全量 pytest 与 scripts 层读数、实现决定交代三栏表。

## 红读数（重锚前，原样复跑）

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run --project apps/api python scripts/verify_audit_evidence.py --strict; echo "EXIT=$?"
```

```text
FAIL  [http] http-09: 错误分类字段 kind 从未被声明，靠 getattr(getattr(exc, "kind", None), "value", ...) 
        apps/api/src/better_resume/main.py:204-204: 0/3 evidence lines in window
PART  [identity_jobs] identity_jobs-03: worker 复制了一份 app 的运行时装配，还为可直接 import 的符号绕道 __import__("better_resume.m
        apps/api/src/better_resume/worker.py:43-68: 12/17 evidence lines in window
        apps/api/src/better_resume/main.py:52-60: 1/17 evidence lines in window
        apps/api/src/better_resume/main.py:217-217: 0/17 evidence lines in window
PART  [interview_engine] IE-10: 追问预算 max_follow_up=2 在五处各写一遍，派生路径固定写 2 而不是继承既有预算
        apps/api/src/better_resume/interview_engine/models.py:135-135: 2/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/flow_store.py:37-37: 3/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/question_service.py:277-283: 2/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/restore_service.py:153-156: 0/14 evidence lines in window
        apps/api/src/better_resume/interview_engine/orm.py:180-181: 2/14 evidence lines in window
        apps/api/src/better_resume/http/interview.py:76-76: 2/14 evidence lines in window
FAIL  [settings_observability] so-04: 五个异常处理器用 getattr 链反推 kind，而不是用异常自己的类型化字段
        apps/api/src/better_resume/main.py:204-204: 0/7 evidence lines in window

verifiable: 118  partial: 2  unverifiable: 2
EXIT=1
```

读数口径：FAIL = 该条所有引证窗口都无证据行（unverifiable），PART = 部分引证窗口无证据行（partial）。

## 重锚清单

| unit / issue | 旧引证（工作区实况） | 新引证 | 依据 |
| --- | --- | --- | --- |
| http-09 | main.py:204（现为注释行） | main.py:220 | 三处 getattr 链现位于 214/220/229；三项证据行仍在 |
| http-10 | interview.py:252-255 | interview.py:257-260 | 两处 gateway_for 同名调用整体 +5 行 |
| http-03 | interview.py:146-150、257-261、381、448-450、455 | interview.py:154-160、262-267、388、448-450、462-464、475（chat.py:151 不变） | 7 处内联 service 构造的现址（`grep -rn 'Service(' http/` 命中 7 处，与标题「7 处」一致） |
| so-04 | main.py:204 | main.py:220 | 同 http-09 的处理器簇 |
| identity_jobs-03 | main.py:52-60、217 | main.py:54-62、233 | llm_gateway import 块整体 +2 行，`build_llm_gateway` 在 61；模块级 `app = create_app()` 在 233 |
| identity_jobs-05 | redis_client.py:58-63、redis_buckets.py:72-74 | redis_client.py:55-60、redis_buckets.py:124-126 | `def redis_client` 在 55；限额器的 redis_client(...) 调用在 124-126 |
| identity_jobs-07 | interview.py:435-439 | interview.py:451-455 | 唯一生产 enqueue 调用点现址 |
| conversation_chat-08 | store.py:119,136 | store.py:130,147 | `seq = row.message_count + 1` 在 130、`row.message_count = seq` 在 147 |
| IE-10 | restore_service.py:153-156 | restore_service.py:156-162 | T19 把派生路径改成内存构造，`return FlowState(` 在 156、`max_follow_up=2,` 在 162；摘录同步改为内存构造形态 |
| LG-09 | resolver.py:236-241 | resolver.py:257-262 | 窗口已落到「绑定缺失」默认分支（仅被 `),` / `)` 噪声命中）；绑定分支的 SceneView 现址 257-262 |
| LG-07 | resolver.py:91-106 | 不动 | 窗口仍含 OpenAiCompatFactory.config_status（96-104），三处凭证判定之一在此，语义未漂 |

与漂移集的差异：漂移集给 identity_jobs-03 的 main.py:53-61 与工作区实况差一行——工作区 `from .llm_gateway import (` 在 54、`build_llm_gateway,` 在 61、`)` 在 62，故按实况取 54-62。其余漂移数字与实况一致。

strict 未报但窗口已错指的（本轮一并重锚，逐条判词见下节）：http-03、http-10、identity_jobs-05、identity_jobs-07、conversation_chat-08、LG-09。

## 验收读数

### 1. `verify_audit_evidence.py --strict` → 全绿

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
uv run --project apps/api python scripts/verify_audit_evidence.py --strict; echo "STRICT_EXIT=$?"
```

```text
verifiable: 122  partial: 0  unverifiable: 0
STRICT_EXIT=0
```

### 2. 结构级读数（引证计数）

```bash
uv run --project apps/api python scripts/verify_audit_evidence.py --structural; echo "STRUCT_EXIT=$?"
```

```text
structure ok: 10 units / 122 issues / 341 citations
STRUCT_EXIT=0
```

引证计数 340 → 341：http-03 的 `where` 补上第 7 处（interview.py:475），与标题「7 处」及 grep 实况对齐。

### 3. MODULE-AUDIT.html 由生成脚本重建

```bash
cd '/root/better resume'
python3 scripts/build_module_audit.py
```

```text
wrote docs/audit/MODULE-AUDIT.html: 10 units, 122 issues
```

一致性核对（HTML 读数 vs units，含旧锚点清零）：

```text
HTML lede: 共 <b>10</b> 个审计单元、<b>122</b> 条问题
units files (excl EXAMPLE): 10 issues: 122
probe 'resolver.py:257-262': in HTML = True
probe 'restore_service.py:156-162': in HTML = True
probe 'main.py:220': in HTML = True
probe 'interview.py:451-455': in HTML = True
probe 'store.py:130,147': in HTML = True
probe 'main.py:54-62': in HTML = True
stale 'resolver.py:236-241': in HTML = False
stale 'restore_service.py:153-156': in HTML = False
stale 'main.py:217': in HTML = False
```

### 4. `bash scripts/verify.sh --layer scripts` → 退出 0

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
bash scripts/verify.sh --layer scripts 2>&1 | tail -10; echo "SCRIPTS_EXIT=${PIPESTATUS[0]}"
```

```text
[14/16] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo 'shell syntax ok'
shell syntax ok
[15/16] uv run --project apps/api python scripts/check_scripts.py
script syntax ok (25 python scripts, SyntaxWarning treated as an error)
[16/16] uv run --project apps/api python scripts/verify_audit_evidence.py --structural
structure ok: 10 units / 122 issues / 341 citations
ALL PASS (16 commands) -- evidence: var/evidence/20261017T065734Z-scripts
SCRIPTS_EXIT=0
```

注：本层在写入 T22-EVIDENCE 全文后复跑过一次，读数同为 ALL PASS（16 commands），两次的证据目录分别是 var/evidence/20261017T065734Z-scripts（units/HTML 定稿后）与 var/evidence/20261017T070037Z-scripts（证据文件定稿后）。

### 5. 权威全量 pytest（隔离库 br_t22_verify，跑完即 drop）

建库：

```bash
cd '/root/better resume/apps/api'
.venv/bin/python - <<'PY'
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect(user="better_resume", password="better_resume", host="127.0.0.1", port=5433, database="postgres")
    await conn.execute("DROP DATABASE IF EXISTS br_t22_verify WITH (FORCE)")
    await conn.execute("CREATE DATABASE br_t22_verify")
    await conn.close()
asyncio.run(main())
PY
```

```text
databases: ['br_t22_verify']
```

全量：

```bash
cd '/root/better resume/apps/api'
export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/br_t22_verify'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/t22-full.xml
uv run pytest -q --junitxml=/tmp/t22-full.xml; echo "FULL_EXIT=$?"
```

```text
FULL_EXIT=0
{'tests': 1018, 'failures': 0, 'errors': 0, 'skipped': 0}
```

跑完 drop：

```text
remaining verify dbs: []
```

## 引证语义抽样复核（38 条，含 LG-09 弱匹配窗口）

抽样口径：覆盖全部 10 个 unit；偏向弱命中窗口（strict 只能证明「窗口含至少一行证据」，弱窗口最可能错指）与被重锚条目；“命中”一列是引用窗口内命中的证据行数/该条证据行总数。

| # | unit / issue | 引用 | 命中 | 窗口内容与断言相符？ |
| --- | --- | --- | --- | --- |
| 1 | ai_resilience ai-02 | redis_buckets.py:23-49 | 1/16 | 相符：窗口是 Lua 脚本的镜像声明与 `TokenBucket.take` 的对应注释，正是「补充算术 Python/Lua 各写一遍」的证据（该条已记 fix_record=fixed）。 |
| 2 | ai_resilience ai-07 | ratelimit.py:42-59 | 8/10 | 相符：`RateLimitDecision` 具名类定义就在窗口里，支持「取令牌却返回裸三元组」。 |
| 3 | ai_resilience ai-10 | singleflight.py:180-190 | 5/11 | 相符：窗口是 `_as_caller` 的类型守卫与 TypeError 抛点，支撑「接口注释没写错误模式/类型不符时怎样」。 |
| 4 | ai_resilience ai-11 | policy.py:26-41 | 15/15 | 相符：`StagePolicies` 五个字段 + `for_stage`，支撑「stage→policy 写三遍」。 |
| 5 | ai_resilience ai-13 | settings/config.py:48-52 | 10/23 | 相符：熔断默认值集中在 settings，是本条「默认数值两处各存一份」的一侧。窗口偏宽（同文件另两段证据在窗口外）。 |
| 6 | conversation_chat conversation_chat-01 | conversation/protocols.py:10-24 | 5/9 | 相符：`ConversationStore` 协议只列 append/history/require_owner 三方法。 |
| 7 | conversation_chat conversation_chat-02 | conversation/store.py:61-72 | 1/6 | 相符：`list_for_user(limit/offset)` 的分页形态正是「取一条我的会话要翻页」；fix_record 后新增的 `get_owned` 在窗口外 79-88，不影响判读。 |
| 8 | conversation_chat conversation_chat-08 | conversation/store.py:130,147 | 逗号列表 | 相符（逐字）：130 `seq = row.message_count + 1`、147 `row.message_count = seq`。 |
| 9 | conversation_chat conversation_chat-09 | chat/service.py:70-79 | 2/5 | 相符：`stream_reply(session: SessionRef)` 签名，支撑「kind 由每个调用者手写」。 |
| 10 | http http-03 | http/interview.py:154-160 | 8/15 | 相符：`QuestionService` 内联构造（含 storage=ResumeStorage(...)）。 |
| 11 | http http-03 | http/interview.py:262-267 | 8/15 | 相符：`AnswerService` 内联构造（locks/hot_state），即「加依赖要改 4 处」的那类点。 |
| 12 | http http-07 | http/interview.py:433-435 | 3/6 | 相符：`_resolve_gateway` 转调 `gateway_for(REPORT_SUMMARY)`，支撑「同签名转调只为换常量」。 |
| 13 | http http-09 | main.py:220 | 1/3 | 相符：`kind = getattr(getattr(exc, "kind", None), ...)` 明摆着；窄锚只覆盖 3 处中的 `unavailable` 一处，是刻意不扩窗的结果。 |
| 14 | http http-10 | http/interview.py:257-260 | 4/4 | 相符（逐字）：两个 `gateway_for` 同用 `payload.model_ref`。 |
| 15 | identity_jobs identity_jobs-03 | main.py:54-62 | 2/17 | 相符：`from .llm_gateway import (... build_llm_gateway,)` 正是「本可直接 import 却绕道 main」的落点。 |
| 16 | identity_jobs identity_jobs-05 | ai_resilience/redis_buckets.py:124-126 | 5/18 | 相符：`redis_client(redis_source, decode_responses=True, socket_timeout=socket_timeout)`，支撑「超时/解码留给调用点各自决定」。 |
| 17 | identity_jobs identity_jobs-06 | identity/deps.py:31 | 1/14 | 相符：`store.touch(session_id, ttl_seconds=settings.session_ttl_seconds)`，支撑「TTL 由调用点线过去」。 |
| 18 | identity_jobs identity_jobs-07 | http/interview.py:451-455 | 5/11 | 相符（逐字）：唯一生产 `enqueue` 调用点整个丢弃返回值。 |
| 19 | identity_jobs identity_jobs-09 | jobs/queue.py:226-228 | 1/8 | 相符：`pending()` 本体，支撑「可观测面在生产里没有消费者」。 |
| 20 | interview_engine IE-03 | restore_service.py:88-89 | 1/15 | 相符：`put(..., ttl_seconds=self._hot_ttl)` 正是「硬编码 TTL 覆盖 settings」。 |
| 21 | interview_engine IE-04 | models.py:48-103 | 21/56 | 相符：窗口是 M0 值对象群（ResumeUpload/Question/...），支撑「协议 + 10 个值对象 + placeholder」的规模描述。 |
| 22 | interview_engine IE-10 | restore_service.py:156-162 | 3/14 | 相符（重锚后，逐字）：内存构造 `FlowState(... max_follow_up=2)`，即派生路径固定写 2。 |
| 23 | interview_engine IE-13 | flow_store.py:18 | 1/37 | 相符：`DEFAULT_MAX_RETRIES = 12` 与该条「裸 asyncio.sleep 重试 12 次」对齐。 |
| 24 | llm_gateway LG-06 | resolver.py:106-113 | 2/10 | 相符：`build_for_model` 走 `registry.resolve`（T20 后的类型化形态），与 fix_record=fixed 的现状一致。 |
| 25 | llm_gateway LG-07 | resolver.py:91-106 | 6/18 | 相符：窗口含 `OpenAiCompatFactory.config_status`（96-104），即三处凭证判定中的第三处；窗口起点多含 __init__ 尾一行，略宽但不错指。 |
| 26 | llm_gateway LG-09 | resolver.py:257-262 | 7/36 | 相符（重锚后）：绑定分支 `target_ref=binding.target_ref`。重锚前 236-241 只被 `),` / `)` 噪声命中，即 P15-7 点名的弱匹配窗口。 |
| 27 | media media-01 | xunfei_ast.py:283-293 | 1/15 | 相符：`_emit_update` 只往 `_event_mapper` 投喂包，与 fix_record=fixed「映射规则抽成一份」的现状一致。 |
| 28 | media media-10 | paraformer_rt.py:117,196,200,238 | 逗号列表 | 相符（逐字）：117 默认值、196 握手、200 首帧 recv、238 静默判定同用 `self._timeout`。 |
| 29 | media media-11 | xunfei_ast.py:96-99 | 3/10 | 相符：窗口是 code 分支的解析处，支撑「错误路径不看 _TERMINAL_CODES」；常量本体在同条 39-40 引证。 |
| 30 | media media-13 | paraformer_rt.py:93-103 | 4/7 | 相符（逐字）：`parse_event -> tuple[str, str, bool]`。 |
| 31 | resume_parser_db resume_parser_db-06 | resume_parser/sections.py:12 | 1/16 | 相符：`from .pdf import TextBlock`，即「章节启发式直接吃 PDF 排版类型」。 |
| 32 | resume_parser_db resume_parser_db-09 | resume_parser/models.py:15-25 | 12/23 | 相符：`Section` 领域模型，支撑「DetectedSection 与 Section 两套模型」。 |
| 33 | resume_parser_db resume_parser_db-11 | tests/resume_parser/conftest.py:19-31 | 12/15 | 相符（逐字）：夹具注释「bold=True … CJK uses a size bump instead」。 |
| 34 | settings_observability so-04 | main.py:220 | 1/7 | 相符：与 http-09 同一行 getattr 链；窄锚只覆盖五处理器中的一处。 |
| 35 | settings_observability so-10 | settings/config.py:79 | 1/8 | 相符：`xunfei_ws_url` 默认端点字面量。 |
| 36 | web web-02 | chat/queries.ts:13 | 1/14 | 相符：`DEFAULT_AUTH_EPOCH = "local"`，即 authEpoch 穿透链的源头。 |
| 37 | web web-06 | api/client.ts:275-298 | 4/8 | 相符：`xhr.onload` 失败 → ApiError 的映射分支。 |
| 38 | web web-11 | audio/transcriptStore.ts:33-43 | 11/36 | 相符：`mergeTranscript` 遗留实现本体（生产无调用者）。 |

判词全部按「窗口里读到的行是否支持该条断言」给出；hits 低但内容相符的（如 1/16、1/15）按相符记——低命中来自证据块跨多文件摘录，不代表错指。

## 实现决定交代

| 决定 | 依据 | 代价 / 边界 |
| --- | --- | --- |
| 只改 `where` 与 `evidence`，结论、issue 文本、severity、fix、fix_record 一律不动 | 票面红线「不改审计结论与 issue 描述」 | 若有断言本身过期，只能在本文件记，不能改 units |
| strict 未报但窗口已错指的 6 条一并重锚（http-03/http-10/identity_jobs-05/identity_jobs-07/conversation_chat-08/LG-09） | 票面范围是「全部引证新鲜度」，不只四条红 | 改动面大于漂移集，故逐条给判词（见抽样表 7/8/10/11/14/16/18/26 行） |
| http-09 / so-04 取漂移集给的窄锚 main.py:220，不扩成 213-229 | 「不许为绿放宽弱匹配」 | 窗口只佐证三处 getattr 中的一处，抽样表已如实记 |
| identity_jobs-03 用 main.py:54-62，而非漂移集的 53-61 | 与工作区实况一致（61 行才是 `build_llm_gateway,`） | 与留档数字差一行，差异写在重锚清单下 |
| LG-09 的 resolver 引证换成绑定分支 257-262，并刷新该段证据摘录（`configured=status.configured` 等） | 旧窗口已被噪声命中、旧摘录文本在工作区不存在 | 属「刷新证据」而非改结论；LG-09 的 why/fix 原样 |
| http-03 `where` 补第 7 处（interview.py:475） | 标题「7 处」与 `grep -rn 'Service(' http/` 的 7 处实况对齐 | 结构级引证计数 340→341，HTML 读数已随之重建 |
| conversation_chat.json / llm_gateway.json 按各自原「平铺 1 空格」缩进重写 | 保持 diff 最小（否则出现 384/517 行纯格式噪声） | 写入按文件既有风格序列化，不是全仓统一 dumper；已核 HEAD 逐字节复现该风格 |
| MODULE-AUDIT.html 由 `scripts/build_module_audit.py` 重建 | 票面红线「HTML 不许手改」 | 生成脚本只印 units/issues，citations 计数靠结构级脚本与 HTML 探针核对 |

## 未验证项

1. 隔离只做了 Postgres（br_t22_verify，跑完已 drop）；`BR_REDIS_URL` 仍指共享 `127.0.0.1:6379/0`，无 Redis 侧隔离（与 T17/T20 同口径）。
2. 全量 1018/0/0/0 是带 p14 在飞改动的工作区读数，不代表干净基线；出票方终验可在干净检出上复跑。
3. strict 是检索式匹配（窗口含至少一行证据即算佐证），无法证明语义相符；本票人工抽样 38/341 处，其余约 303 处未逐条语义复核——那是 P15-7（工具强化）的范围。
4. 逗号列表引证（conversation_chat-01/08、media-05/10/13、media-11）不进逐字级，只由结构级验可解析与行区间存在；本轮抽样了 conversation_chat-08、media-10、media-13、media-11。
5. HTML 页面本身不打印 citations 计数；只能以「lede 10 单元/122 问题 + 新锚点全在、旧锚点全无」间接核对，未对 HTML 全文做逐字引证比对。
6. p14 在飞改动未动、未核；本票只改 `docs/audit/units/`、`docs/audit/MODULE-AUDIT.html` 与本证据文件。
