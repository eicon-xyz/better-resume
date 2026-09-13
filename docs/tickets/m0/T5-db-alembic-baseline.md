# T5 — DB 连接 + Alembic 基线（alembic check 绿）

- blocking：T6（需要一个真 Postgres 实例）

## 目标

按 D02 落 SQLAlchemy 2.0 async + Alembic 迁移骨架，且 `alembic check` 在本地与 CI 都可跑绿。

## 交付物

- `better_resume/db/session.py`：async engine + `async_sessionmaker` 挂 lifespan、
  统一 `get_session` 依赖、`Base`（DeclarativeBase）
- `apps/api/alembic.ini` + `apps/api/migrations/env.py`（async 模板）+ `script.py.mako`
- 基线迁移：`migrations/versions/0001_baseline.py`（M0 无表，只建立 revision 链起点）
- 测试：`tests/test_migrations.py`（连真库时跑；无库则 skip 并说明）

## 验收

| 命令 | 期望 |
| --- | --- |
| `docker compose up -d --wait postgres` | postgres healthy |
| `uv run alembic upgrade head` | 建 `alembic_version` 且 revision = 0001 |
| `uv run alembic check` | `No new upgrade operations detected.`（exit 0） |
| `uv run alembic downgrade base && uv run alembic upgrade head` | 可逆 |

## 形态提议（待确认）

- M0 用**空基线**（不建业务表）：T3 的会话在 Redis，users 表留 M1；这样 `alembic check`
  在 M0 就是稳态（metadata 与 head 一致）。
- CI 中 Postgres 走 GitHub Actions service container；本地走 compose 的 postgres。

## 不做

- 不建业务表、不引扩展、不做数据迁移脚本。
