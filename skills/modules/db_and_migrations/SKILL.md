# db & migrations

## 职责

SQLAlchemy 2.0 async 引擎/会话工厂 + Alembic 迁移与默认数据。

## 对外接口

`build_engine` / `build_session_factory`（挂在 lifespan）、`Base`、`migrations/versions/*`。

## 不变量

1. 模型与迁移必须同步：CI 跑 `alembic check`，改模型不写迁移直接红。
2. 默认数据（模型注册表、场景绑定）写在**迁移**里，不在应用启动时插入（可复现）。
3. 一个事务一个 session；跨事务的状态转移靠 version CAS，不靠"读-改-写"。
4. JSONB 用 GIN `jsonb_path_ops` 索引；会话/消息的归属字段必须建索引。

## 已知陷阱

- `sqlalchemy.text` 会被同名映射列遮蔽（M2 踩过：`'MappedColumn' object is not callable`）→ 用 `text as sa_text`。
- "脚本说已经改了"不算证据：迁移与文档都要用 `alembic check` / `git diff --stat` 复核
  （M4 P13：README 的更新在一次 `git reset --hard` 里丢过两个里程碑）。
- 本地原生 Postgres 在 5433（Docker 不可用时期的产物），compose 里是 5432；测试靠 `BR_DATABASE_URL`。
- 迁移的 downgrade 也要能跑（drill/回滚演练会用到）。

## 测试地图

`tests/test_migrations.py`（升级一致性、`alembic check`）、各模块的 store 测试（真库）。

## 常见变更配方

加表：ORM → `alembic revision --autogenerate` → 人工校对（索引/默认值/降级）→ 用例 → `alembic check`。
