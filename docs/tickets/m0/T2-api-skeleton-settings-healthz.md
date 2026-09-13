# T2 — apps/api 骨架 + settings + /healthz

- blocking：T1

## 目标

可 `uv run` 起服务的 FastAPI 应用工厂 + 配置外置 + 结构化日志/request_id + 健康检查端点。

## 交付物

- `better_resume/main.py`：`create_app()` 工厂（lifespan 内初始化 async_sessionmaker、Redis 客户端）
- `better_resume/settings/`：pydantic-settings `Settings`（env 前缀、`.env` 支持、启动即校验必填项）；
  `.env.example` 与 settings 字段一一对应（含 compose 开发默认值，无真实密钥）
- `better_resume/observability/`：structlog JSON 配置 + `request_id` 中间件
  （contextvars 绑定，响应头 `X-Request-Id`，缺失则生成、有则透传）
- `better_resume/http/health.py`：`GET /healthz` -> `{"status":"ok"}`（后续 M 再加深依赖探测）
- 测试：`tests/test_healthz.py`、`tests/test_settings.py`、`tests/test_request_id.py`

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run ruff check . && uv run ruff format --check .` | exit 0 |
| `uv run pytest -q` | 全绿（含 /healthz、request_id 透传/生成、settings 校验失败用例） |
| `uv run uvicorn better_resume.main:app --port 8000` + `curl -fsS localhost:8000/healthz` | 200 `{"status":"ok"}`，响应头含 `X-Request-Id` |
| 日志采样 | JSON 行含 `request_id`、`event`、`level` |

## 形态提议（待确认）

- 单体同域：`/healthz` 不带 `/api` 前缀；业务端点后续统一挂 `/api/v1`。
- request_id 存 contextvar，不引 OpenTelemetry（D17）。

## 不做

- 不写业务端点、不建 DB 表、不引 Celery/worker。
