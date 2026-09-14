# repo-map —— 要改 X 先看哪（M6-T7）

> 用法：先在这里找到"改什么"，再看对应模块的 `SKILL.md` 里的不变量与陷阱。
> 每个后端模块都有一份 `skills/modules/<name>/SKILL.md`（migrations 在 `db_and_migrations/`）；
> 前端不单列模块，走最后一行的入口 + `api-index` 里的"前端路由"表。

| 要改的东西 | 先看 | 不变量 / 陷阱 | 测试 |
| --- | --- | --- | --- |
| 配置项、环境变量、默认值 | `skills/modules/settings/SKILL.md`, `apps/api/src/better_resume/settings/config.py` | 前缀 `BR_`；嵌套用 `__`；密钥只从环境变量读；嵌套类别放错（M4 P8） | `apps/api/tests/test_settings.py` |
| 登录、cookie 会话、WS 票据 | `skills/modules/identity/SKILL.md`, `identity/` | 会话 id 用 secrets 生成；cookie HttpOnly；WS 票据一次性（Redis Lua 原子取删） | `tests/test_identity.py`, `tests/test_ws_ticket.py` |
| 会话消息、seq、历史分页 | `skills/modules/conversation/SKILL.md`, `conversation/` | 消息唯一归属在 conversation；seq 在事务里分配；归属失败一律 404 | `tests/test_conversation_store.py`, `tests/test_chat_api.py` |
| 模型注册表、供应商调用、结构化输出 | `skills/modules/llm_gateway/SKILL.md`, `llm_gateway/` | 两个 adapter 走同一契约；schema 强校验；**禁止别名回退**（M5 P0） | `tests/llm_gateway/`, `tests/test_adapter_contract.py` |
| 场景绑定、换供应商 | `llm_gateway/{scenes,binding_store,resolver}.py`, `http/scenes.py` | 服务层不感知供应商；绑定改完失效缓存；密钥不在 DB | `tests/llm_gateway/test_scene_*.py`, `tests/test_scene_routing.py` |
| 单飞 / 熔断 / 舱壁 / 超时 / 限流 | `skills/modules/ai_resilience/SKILL.md`, `ai_resilience/` | 四条链路只调 `run(stage, key, fn)`；只有一个重试 owner；Redis 单飞先查结果再抢 owner（M6 P2） | `tests/ai_resilience/`, `tests/test_distributed_flight.py` |
| 面试状态机、答题、追问、报告 | `skills/modules/interview_engine/SKILL.md`, `interview_engine/` | 两层状态机是唯一写入口；幂等靠 `(session_id, request_id)`；题级锁保证可重答 | `tests/interview_engine/`, `tests/test_interview_*_api.py` |
| 简历解析 | `skills/modules/resume_parser/SKILL.md`, `resume_parser/` | **不走 LLM**；扫描件/坏文件给带 code 的明确错误；fixture 用代码生成（M4 P7） | `tests/resume_parser/` |
| 转写与 TTS | `skills/modules/media/SKILL.md`, `media/` | 句池归并是纯函数；协议细节不出 adapter；一个通道两个消费方 | `tests/media/`, `tests/test_media_ws.py` |
| HTTP 层、错误映射、中间件 | `skills/modules/http/SKILL.md`, `http/` | 业务异常 → 明确状态码（404/409/422/503/504）；限流 fail-open；每响应带 `X-Instance-Id` | `tests/test_*_api.py`, `tests/test_ratelimit_http.py` |
| 迁移与表结构（migrations） | `skills/modules/db_and_migrations/SKILL.md`, `apps/api/migrations/versions/` | 迁移必须与模型同步（`alembic check`）；默认数据写进迁移；downgrade 也要能跑 | `tests/test_migrations.py` |
| 作业队列与 worker | `jobs/queue.py`, `worker.py` | 幂等键去重；失败退避重试；超限进死信；未 ACK 的任务可被接管 | `tests/test_job_queue.py`, `tests/test_worker_health.py` |
| 部署（compose / nginx / 非 root） | `compose.yaml`, `deploy/nginx.conf`, `apps/api/Dockerfile` | nginx 是唯一入口；api 无宿主端口（可 `--scale api=2`）；容器非 root；SSE 不缓冲 | `scripts/compose_smoke.sh`, `tests/test_deploy_manifest.py` |
| 前端页面、路由、API 客户端（web） | `apps/web/src/App.tsx`, `apps/web/src/api/client.ts`, `apps/web/src/chat/`, `apps/web/src/interview/`, `apps/web/src/audio/` | 端点/路由改动要重新生成 `skills/api-index/generated-api-index.md`；转写不覆盖手写文本；播放器单例 | `pnpm -C apps/web test`, `apps/web/src/**/*.test.tsx` |
| 上下文与求职材料 | `docs/tickets/*/ACCEPTANCE.md`（验收与偏差）、`docs/tickets/*/PROBLEMS.md`（问题台账） | 证据优先于叙述；未验证项必须写出来 | 人工：按本表走 2 跳能不能到入口 |

## 两跳示例（T7 验收用）

- "限流 429 之后前端为什么还清空输入？" → 本表 HTTP 行 → `skills/modules/http/SKILL.md` → 陷阱指向 M3 P10。
- "换供应商要改哪些文件？" → 场景绑定行 → `llm_gateway/` 三个文件 + 契约测试。
- "为什么 kill 掉一个 api 实例后还能继续答题？" → `ai_resilience` 行 + `interview_engine` 的热层不变量。
