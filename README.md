# better-resume

AI 模拟面试平台（对 AI-Meeting / 码上面试平台的重写）：Python 3.12 + FastAPI +
SQLAlchemy 2.0(async) + Postgres/Redis + React 19 + Vite。

## 当前状态

**M0 已完成（2026-09-13）**：monorepo 结构 + compose 三服务（postgres/redis/api，全健康检查）+
CI 双 job + settings/identity 最小可用 + 六个后端模块 Protocol 占位。
验收证据见 docs/tickets/m0/ACCEPTANCE.md；下一步 M1（conversation 真表 + llm-gateway +
chat SSE 页）。

## 必读

1. docs/DECISIONS.md —— 17 项技术栈/范围决议（开工依据，冲突时以它为准）
2. docs/ai-meeting-architecture-analysis.md —— 原项目全景分析（§12 为新项目模块蓝图）
3. docs/tickets/m0/ —— M0 票据拆分、验收标准与待确认项

## 结构

```
apps/api      # FastAPI 模块化单体（src/better_resume/：settings/identity/conversation/
              #   llm_gateway/ai_resilience/interview_engine/resume_parser/media/db）
apps/web      # React SPA（M1 起：api-client / interview-session reducer / stream-renderer）
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

# 三服务
docker compose up -d --wait
```

## 测试纪律

只 mock 系统边界（LLM / 时钟 / Redis / 讯飞），不 mock 内部模块。
M0 为「可导入 / 合约」冒烟测试；红-绿 TDD 从 M1 第一张票据开始。
