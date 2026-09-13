# better-resume

AI 模拟面试平台：Python 3.12 + FastAPI +
SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**M4 已完成（2026-09-14）**：media 语音链路 —— 句池归并（apd / rpl 删区间 / 时间重叠+文本演化 /
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
下一步 M5：星云 WorkflowAdapter（双 adapter 对照）。

## 必读

1. docs/DECISIONS.md —— 17 项技术栈/范围决议（开工依据，冲突时以它为准）
2. docs/ai-meeting-architecture-analysis.md —— 原项目全景分析（§12 为新项目模块蓝图）
3. docs/tickets/m4/ —— 当前里程碑票据与验收证据（含 PROBLEMS.md 问题台账）；
   M0–M3 存档在 docs/tickets/m0|m1|m2|m3/

## 结构

```
apps/api      # FastAPI 模块化单体（src/better_resume/：settings/identity/conversation/
              #   llm_gateway/ai_resilience/interview_engine/resume_parser/media/db）
apps/web      # React SPA（api-client / stream-renderer / chat 页 / 面试三段页 / 自绘雷达）
docs          # 决议、架构分析、票据
skills        # 仓库自描述层（repo-map + 每模块 SKILL.md，M6）
```

## 本地开发

```bash
# 后端
cd apps/api && uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run uvicorn better_resume.main:app --port 8000

# 前端
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

# 三服务（改完后端记得 --build）
docker compose up -d --build --wait
```

### 契约变更流程（D17）

后端是唯一 Schema 源；改完 Pydantic 模型后必须重生成两处生成物并一起提交：

```bash
uv run --project apps/api python apps/api/scripts/export_openapi.py   # 更新 openapi.json
pnpm -C apps/web gen:api                                              # 更新 src/api/schema.d.ts
```

CI 会用 `--check` / `check:api` 拦住忘记重生成的提交。

## 测试纪律

只 mock 系统边界（LLM / 时钟 / Redis / 讯飞），不 mock 内部模块。
M0 为「可导入 / 合约」冒烟测试；红-绿 TDD 从 M1 第一张票据开始。
