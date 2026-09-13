# better-resume

AI 模拟面试平台：Python 3.12 + FastAPI +
SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**M1 已完成（2026-09-13）**：conversation 落库（Postgres + JSONB）、llm-gateway（模型注册表 +
OpenAI 兼容适配器 + schema 强校验）、chat SSE 链路（15s 心跳 / reasoning 分流 / 幂等）、
OpenAPI → TS 类型生成、前端 chat 页（打字机 + 深度思考面板 + 历史回放）。
后端 94 tests / 前端 65 tests 全绿；验收证据见 docs/tickets/m1/ACCEPTANCE.md。

M0（骨架）证据见 docs/tickets/m0/ACCEPTANCE.md。下一步 M2：面试引擎（resume-parser +
状态机 + 出题/评分/追问 + 报告）。

## 必读

1. docs/DECISIONS.md —— 17 项技术栈/范围决议（开工依据，冲突时以它为准）
2. docs/ai-meeting-architecture-analysis.md —— 原项目全景分析（§12 为新项目模块蓝图）
3. docs/tickets/m1/ —— 当前里程碑票据与验收证据（M0 存档在 docs/tickets/m0/）

## 结构

```
apps/api      # FastAPI 模块化单体（src/better_resume/：settings/identity/conversation/
              #   llm_gateway/ai_resilience/interview_engine/resume_parser/media/db）
apps/web      # React SPA（api-client / stream-renderer / chat 运行态与页面；面试页 M2）
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
