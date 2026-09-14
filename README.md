# better-resume

AI 模拟面试平台：Python 3.12 + FastAPI +
SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**M6 已完成（2026-09-14）**：分布式模式 + 容量 + skills 知识库 —— Redis 分布式锁与单飞（先查结果再抢锁、
owner token、租约续租、fencing 拒写、结果回放）、会话热态（`source=hot/derived` + 写路径失效）、
Redis Stream worker（幂等去重 / 重试 / 死信 / XPENDING+XCLAIM 崩溃接管，报告总结异步化）、
compose 最终形态（nginx 入口 + api 可 `--scale` + 一次性 migrate 服务 + 非 root + 共享卷）、
自研压测脚本与容量报告、skills 自描述层（repo-map + 10 份模块 SKILL.md + 生成式 API 索引 + CI 漂移检查）。
**硬验收**：`bash scripts/kill_instance_drill.sh` —— 面试进行中 kill 掉正在服务的 api 实例，
另一实例接管且题号/已答/分数/追问/冻结报告全部一致（实测 kill→恢复 237 ms）；
部署面 `bash scripts/compose_smoke.sh` 全绿。后端 648 / 前端 158 全绿；
**真模型高并发未压测**（容量报告 §2.4 为空），证据与未验证项见 docs/tickets/m6/ACCEPTANCE.md，
问题台账见 docs/tickets/m6/PROBLEMS.md（P0–P14）。

**M5 已完成（2026-09-14）**：星云 WorkflowAdapter 双 adapter 对照 —— 五个业务场景（对话/出题/评分/追问/报告总结）
各自一行绑定（DB 表 + 进程内缓存 + GET/PUT /api/v1/scenes），切换供应商**不改业务代码**（diff 仅 7 行可选参数）；
第二个 adapter 按 §4.1.8 实现星云工作流（Bearer apiKey:apiSecret / flow_id·history·parameters / SSE 归一 / Pydantic 强校验，
**拒绝旧项目的别名回退**）；一套 10 条契约 × 2 实现 + 突变校验；前端 /settings/ai 面板。
后端 528 / 前端 158 全绿；**星云真机未验证（本机无凭据）**，证据与未验证项见 docs/tickets/m5/ACCEPTANCE.md，
问题台账见 docs/tickets/m5/PROBLEMS.md（P0–P4）。

**M4 已完成**：media 语音链路 —— 句池归并（apd / rpl 删区间 / 时间重叠+文本演化 /
尾缀合并 / final，D16 亮点③）、讯飞 AST WebSocket adapter（HmacSHA1 签名、1280B·40ms 推流、cn.st 解析、
有界重连）、一次性 WS 票据（D11）、edge-tts 播报（内容寻址缓存 + 单例播放器 + 独立 Stage.TTS 接入韧性链）、
浏览器端 16k PCM 采集与转写消费（一个通道两个消费方，转写不覆盖手写文本）。
后端 473 / 前端 152 全绿；**讯飞真机与真实浏览器人工验证待做（本机缺凭据）**，
证据与未验证项见 docs/tickets/m4/ACCEPTANCE.md，问题台账见 docs/tickets/m4/PROBLEMS.md（P0–P12）。

**M3 已完成（2026-09-13）**：ai-resilience 真实现 —— run(stage, key, fn) 一个方法藏着进程内单飞（含流式广播）、
按 stage 熔断、舱壁、注入时钟超时与分桶限流；四条 AI 链路全部接上；失败三态映射 504/503，限流 429 + Retry-After。
证据 docs/tickets/m3/ACCEPTANCE.md。

**M2 已完成**：确定性简历解析 + 两层状态机 + 出题→答题→评分→追问 + 冻结报告（四维雷达）+ 前端三段页面。
证据 docs/tickets/m2/ACCEPTANCE.md。

历史：M1 docs/tickets/m1/ACCEPTANCE.md，M0 docs/tickets/m0/ACCEPTANCE.md。
M6 是最后一个里程碑（§12.4 收口）；后续欠账是真机凭据与生产网络类验证（见 M6 ACCEPTANCE §6）。

## 必读

1. **docs/HANDOFF.md —— 交接文档**（当前状态 / 怎么跑 / 本机坑 / 凭据政策 / 欠账 / 下一步），换窗口先读它
2. docs/DECISIONS.md —— 17 项技术栈/范围决议（开工依据，冲突时以它为准）
3. docs/ai-meeting-architecture-analysis.md —— 原项目全景分析（§12 为新项目模块蓝图）
4. docs/tickets/v1-verification/ —— 当前阶段（验证欠账）：README（进度）+ 票据 + EVIDENCE + PROBLEMS(P17–P21)
5. 历史：M6 docs/tickets/m6/（ACCEPTANCE / PROBLEMS / T5-EVIDENCE），M0–M5 在 docs/tickets/m0|m1|m2|m3|m4|m5/

## 结构

```
apps/api      # FastAPI 模块化单体（src/better_resume/：settings/identity/conversation/
              #   llm_gateway/ai_resilience/interview_engine/resume_parser/media/db）
apps/web      # React SPA（api-client / stream-renderer / chat 页 / 面试三段页 / 自绘雷达）
docs          # 决议、架构分析、票据、容量报告（docs/perf）、简历草稿（docs/resume）
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

# 前端
# 前端（在仓库根跑；-C 的路径相对当前目录，从 apps/api 跑要用 ../web）
cd "$(git rev-parse --show-toplevel)"
pnpm -C apps/web lint && pnpm -C apps/web typecheck && pnpm -C apps/web test -- --run

# 本地数据库与缓存（本机无 Docker 时）：原生 Postgres 5433 + 原生 Redis 6379，
# 用 BR_DATABASE_URL / BR_REDIS_URL 指定；CI 与 compose 使用各自的默认值。

# M3 韧性参数（全部有默认值，重启生效）：BR_RESILIENCE__* / BR_RATE_LIMIT__*；
#   运行态快照（需登录）：GET /api/v1/resilience/stats
#   证据脚本：uv run --project apps/api python apps/api/scripts/resilience_smoke.py

# M4 语音（默认 adapter=scripted，本地/CI 无需凭据；真机需要讯飞三件套）：
#   BR_MEDIA__TRANSCRIPTION_ADAPTER=xunfei|scripted
#   BR_XUNFEI_APP_ID / BR_XUNFEI_ACCESS_KEY_ID / BR_XUNFEI_ACCESS_KEY_SECRET（只放 gitignored .env）
#   WS：POST /api/v1/auth/ws-ticket → WS /api/v1/media/transcribe?ticket=...
#   TTS：POST /api/v1/media/tts → GET /api/v1/media/tts/{digest}.mp3（同源 audio 带 cookie）
#   冒烟：uv run --project apps/api python apps/api/scripts/media_smoke.py --scripted

# M5 场景绑定（换供应商不发版）：
#   GET /api/v1/scenes 查看五个场景的绑定；PUT /api/v1/scenes/{scene} 切换（需登录）
#   星云凭据只从环境变量读：XINGCHEN_API_KEY / XINGCHEN_API_SECRET；每场景 flow_id 存在绑定行的 target_ref
#   前端入口：/settings/ai
#   对照冒烟：uv run --project apps/api python apps/api/scripts/adapter_smoke.py --scene answer_evaluation [--real-xingyun]

# 五服务（改完后端记得 --build）：nginx 是唯一入口（:8080），api 不对外发端口
docker compose up -d --build --wait
```

## 部署形态（M6-T5，D07 最终形态）

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

SSE 检查用 `smoke` profile 里的确定性假供应商（`scripts/fake_openai.py`，故意延迟首帧，
所以能同时看到 API 心跳帧与模型分片），**不消耗真实供应商额度**。

### 契约变更流程（D17）

后端是唯一 Schema 源；改完 Pydantic 模型后必须重生成两处生成物并一起提交：

```bash
uv run --project apps/api python apps/api/scripts/export_openapi.py   # 更新 openapi.json
pnpm -C apps/web gen:api                                              # 更新 src/api/schema.d.ts
```

CI 会用 `--check` / `check:api` 拦住忘记重生成的提交。

## 协作流程（每个阶段都按这个节奏）

1. **先出提案**：范围 / 不做 / 交付物 / 测试与验收口径（放 `docs/tickets/mN/`），**等确认再动工**。
2. **确认后执行**：红-绿 TDD，小步提交说清 WHAT，难题即时记 `PROBLEMS.md`。
3. **完成后交验收包**：`ACCEPTANCE.md`（可复跑命令 + 原始输出 + 未验证项 + 偏差清单）+ 容量/证据文档。
4. **由人验收**：AI 不自行宣布完成、不擅自合并；验收通过后再开 PR / 合并 / 进入下一阶段。

## 测试纪律

只 mock 系统边界（LLM / 时钟 / Redis / 讯飞），不 mock 内部模块。
M0 为「可导入 / 合约」冒烟测试；红-绿 TDD 从 M1 第一张票据开始。
