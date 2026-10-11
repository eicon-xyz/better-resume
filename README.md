# better-resume

AI 模拟面试平台：Python 3.12 + FastAPI + SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**全部里程碑已合并，`main` CI 绿，没有在飞阶段。** 代码即事实——分层验证入口 `bash scripts/verify.sh --list`。

- **后端**：确定性简历解析（不靠 LLM）→ 两层状态机 → 出题 / 答题 / 评分 / 追问 → 冻结报告（四维雷达）；
  四条 AI 链路全部走 `ai_resilience`（单飞 / 熔断 / 舱壁 / 超时 / 限流）。
- **语音**：讯飞 AST（流式句池归并）、百炼 Qwen-Audio 批量、百炼 Paraformer 实时三条链路，由
  `BR_MEDIA__TRANSCRIPTION_ADAPTER` 选择；TTS 走 edge-tts + 内容寻址缓存。
- **前端**：React SPA（api-client / stream-renderer / chat 页 / 面试三段页 / 自绘雷达）。
- **分布式**：Redis 分布式锁与单飞（先查结果再抢锁、租约续租、fencing 拒写、结果回放）、会话热态、
  Redis Stream worker（幂等去重 / 重试 / 死信 / 崩溃接管）、N 副本共享对外配额（D19）。
- **部署**：单机 docker compose，nginx 是唯一入口；`bash scripts/kill_instance_drill.sh` 证明 kill 掉在服务的实例后状态一致。
- **验证网**：CI 双 job 与本地走同一份分层命令；`nightly`（每日 02:30 UTC）与 `weekly-full`（周日 03:00 UTC）定时兜底。
- **未验证项**（真机凭据类、浏览器矩阵、并发上限等）见 `docs/HANDOFF.md` §6。

## 必读

1. **`docs/HANDOFF.md`** —— 当前状态 / 怎么跑 / 本机坑 / 未验证清单；换窗口先读它
2. **`AGENTS.md`** —— 项目全貌、开发规范与协作流程（含硬规则）
3. **`GLOSSARY.md`** —— 域词汇表（术语）
4. `docs/DECISIONS.md` —— 技术栈与范围决议（冲突时以它为准）
5. `skills/repo-map/SKILL.md` —— 「改 X 先看哪」的导航
6. `docs/history_docs/` —— 已收口阶段的历史（票据 / 验收包 / 问题台账 / 经验流水），**只用于回溯，不是当前状态**

## 结构

```
apps/api      # FastAPI 模块化单体（src/better_resume/：settings/identity/conversation/
              #   llm_gateway/ai_resilience/interview_engine/resume_parser/media/db）
apps/web      # React SPA（api-client / stream-renderer / chat 页 / 面试三段页 / 自绘雷达）
docs          # 交接 / 决议 / 审计 / 容量报告 / 在飞阶段票据；历史归档在 docs/history_docs/
skills        # 仓库自描述层（repo-map + 每模块 SKILL.md + 生成式 API 索引）
```

## 本地开发

```bash
# 后端（uv 常装在 ~/.local/bin，root 新 shell 里记得带上）
export PATH="$HOME/.local/bin:$PATH"
cd apps/api && uv sync
uv run ruff check . && uv run ruff format --check .

# 测试要一个可达的 Postgres + Redis：本机原生是 5433 / 6379（CI 与 compose 用各自默认值）。
# 不导出这两个变量时，需要数据库的用例会 skipped（postgres not reachable），不会假装通过。
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q
uv run uvicorn better_resume.main:app --port 8000

# 前端（在仓库根跑；-C 的路径相对当前目录，从 apps/api 跑要用 ../web）
cd "$(git rev-parse --show-toplevel)"
pnpm -C apps/web lint && pnpm -C apps/web typecheck && pnpm -C apps/web test -- --run

# 韧性参数（全部有默认值，重启生效）：BR_RESILIENCE__* / BR_RATE_LIMIT__*；
#   运行态快照（需登录）：GET /api/v1/resilience/stats

# 语音（默认 adapter=scripted，本地/CI 无需凭据；真机需要讯飞三件套）：
#   BR_MEDIA__TRANSCRIPTION_ADAPTER=xunfei|scripted
#   BR_XUNFEI_APP_ID / BR_XUNFEI_ACCESS_KEY_ID / BR_XUNFEI_ACCESS_KEY_SECRET（只放 gitignored .env）
#   WS：POST /api/v1/auth/ws-ticket → WS /api/v1/media/transcribe?ticket=...
#   TTS：POST /api/v1/media/tts → GET /api/v1/media/tts/{digest}.mp3（同源 audio 带 cookie）

# 场景绑定（换供应商不改业务代码）：
#   GET /api/v1/scenes 查看五个场景的绑定；PUT /api/v1/scenes/{scene} 切换（需登录）
#   前端入口：/settings/ai

# 五服务（改完后端记得 --build）：nginx 是唯一入口（:8080），api 不对外发端口
docker compose up -d --build --wait
```

## 部署形态（D07）

```
浏览器 ──▶ nginx :8080 ──▶ api :8000（可 --scale api=2，进程内锁/热状态/单飞走 Redis）
                │                    │
                │                    ├── postgres:16    （会话、报告、场景绑定、模型注册表）
                └── 静态 SPA          ├── redis:7        （锁、热状态、任务流、WS 票据、心跳）
                     /api/ 反代        └── worker        （python -m better_resume.worker，报告总结）
```

- **入口**：`http://127.0.0.1:8080`（`NGINX_PORT` 可改）。nginx 提供 SPA（`try_files` 回退）、
  `/api/` 反代（`proxy_buffering off` + `Upgrade`/`Connection`，SSE 与 WS 都不过缓冲）、`/healthz`。
- **健康检查**：api 打 `/healthz`；worker 没有端口，改为刷新 Redis 心跳键 `br:jobs:health`，
  容器健康检查是 `python -m better_resume.worker --health`；nginx 依赖 `api: service_healthy`。
- **实例标识**：每个响应带 `X-Instance-Id`（默认容器 hostname），轮询与 kill 演练都靠它。
- **扩缩容**：`docker compose up -d --scale api=2 --wait`；api 不发布宿主端口，所以不会端口冲突。
- **受限网络**：镜像站前缀写进 `.env` 的 `BR_LIBRARY_PREFIX` / `BR_UV_IMAGE`（见 `.env.example`），
  仓库默认仍是上游原始 tag。
- **冒烟（真实起栈，走 nginx 打完整链路）**：

```bash
bash scripts/compose_smoke.sh          # 起栈 + REST/SSE/WS + 非 root + 双实例轮询，全部 PASS/FAIL
```

SSE 检查用 `smoke` profile 里的确定性假供应商（`apps/api/scripts/fake_openai.py`，故意延迟首帧，
所以能同时看到 API 心跳帧与模型分片），**不消耗真实供应商额度**。

### 契约变更流程（D17）

后端是唯一 Schema 源；改完 Pydantic 模型后必须重生成两处生成物并一起提交：

```bash
uv run --project apps/api python apps/api/scripts/export_openapi.py   # 更新 openapi.json
pnpm -C apps/web gen:api                                              # 更新 src/api/schema.d.ts
```

CI 会用 `--check` / `check:api` 拦住忘记重生成的提交。

## 协作流程

1. **先出提案**：范围 / 不做 / 交付物 / 测试与验收口径（放 `docs/tickets/<stage>/README.md`），**等确认再动工**。
2. **确认后执行**：红-绿 TDD，改动留在工作区并说清 WHAT，难题即时记该阶段的 `PROBLEMS.md`。
3. **完成后交验收包**：`ACCEPTANCE.md`（可复跑命令 + 原始输出 + 未验证项 + 偏差清单）。
4. **由人验收**：验收通过并**明确下令**后才提交 / 推送 / 开 PR；AI 不自行宣布完成、不擅自合并。
5. **阶段收口后归档**：整个票据目录移入 `docs/history_docs/tickets/`。

## 测试纪律

只 mock 系统边界（LLM / 时钟 / Redis / 讯飞 / 浏览器音频 / IPC），不 mock 内部模块；
断言不依赖 shell 里恰好存在的代理变量 / PATH / DB 地址（hermetic）。红-绿 TDD：先有会红的用例，再写实现。
