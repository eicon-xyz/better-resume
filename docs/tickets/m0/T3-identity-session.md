# T3 — identity cookie session 骨架

- blocking：T2

## 目标

按 D11 落最小可用身份层：HttpOnly Cookie session + Redis 存储 + 30 天滑动过期；
WS 一次性 ticket 只留接口（分布式实现归 M6）。

## 交付物

- `better_resume/identity/models.py`：`Principal`（user_id / roles）、`SessionRecord`
- `better_resume/identity/store.py`：`SessionStore` Protocol（`create` / `get` / `touch` / `delete`）
- `better_resume/identity/redis_store.py`：`RedisSessionStore`（TTL = 30 天，读时滑动续期）
- `better_resume/identity/memory_store.py`：`InMemorySessionStore`（测试与无 Redis 场景）
- `better_resume/identity/cookies.py`：`set_session_cookie` / `clear_session_cookie`
  （HttpOnly、SameSite=Lax、Secure 由 settings 控制、Path=/）
- `better_resume/identity/deps.py`：`current_principal` FastAPI 依赖（无/过期 -> 401）
- `better_resume/identity/tickets.py`：`issue_ws_ticket` / `consume_ws_ticket` 接口 + 占位实现
- 端点骨架：`POST /api/v1/auth/session`（M0 为 dev 直发会话，body `{user_id}`）、
  `GET /api/v1/auth/me`、`DELETE /api/v1/auth/session`
- 测试：cookie 属性、滑动过期（假时钟）、401 路径、登出后会话失效

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_identity*` | 全绿；Redis 用 fakeredis/内存 store（系统边界可 mock） |
| `curl -i -X POST localhost:8000/api/v1/auth/session -d '{"user_id":"u1"}'` | 200 + `Set-Cookie: ... HttpOnly; SameSite=lax` |
| 带 cookie 请求 `/auth/me` / 不带 cookie | 200 返回 principal / 401 |

## 形态提议（待确认）

- M0 **不建 users 表**（会话主体由请求指定），真实登录流与用户表归 M1/M2 —— 若你要求 M0 落 users 表，
  则本票并入 T5 并加一张表。
- 端点路径统一 `/api/v1/auth/*`；WS ticket 在 M0 只保证接口存在且可导入。

## 不做

- JWT、OAuth、密码哈希、注册/登录 UI、Redis Lua 单飞。
