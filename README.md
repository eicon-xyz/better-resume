# better-resume

AI 模拟面试平台：Python 3.12 + FastAPI +
SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**M2 已完成（2026-09-13）**：确定性简历解析（pdfplumber + 章节启发式 + CJK 回退，不靠 LLM）、
两层状态机（会话生命周期 / 答题流程，转移表穷举 + version CAS）、出题→答题→评分→追问全链路
（schema 强校验 / requestId 幂等 / 题级锁 / 规则链追问）、恢复与冻结报告（四维雷达 + 逐题回放）、
前端三段页面（上传 → 面试房间 → 报告，自绘 SVG 雷达）。
后端 324 tests / 前端 104 tests 全绿；验收证据见 docs/tickets/m2/ACCEPTANCE.md。

历史：M1（对话链路）docs/tickets/m1/ACCEPTANCE.md，M0（骨架）docs/tickets/m0/ACCEPTANCE.md。
下一步 M3：ai-resilience 真实现（单飞 + 熔断 + 限流）。

## 必读

1. docs/DECISIONS.md —— 17 项技术栈/范围决议（开工依据，冲突时以它为准）
2. docs/ai-meeting-architecture-analysis.md —— 原项目全景分析（§12 为新项目模块蓝图）
3. docs/tickets/m2/ —— 当前里程碑票据与验收证据（M0/M1 存档在 docs/tickets/m0|m1/）

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
