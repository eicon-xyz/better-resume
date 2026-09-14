# identity

## 职责

cookie 会话（Redis 或内存）+ WS 一次性票据。**不做**注册/密码/JWT（D11）。

## 对外接口

`Principal`、`current_principal` 依赖、`build_session_store` / `build_ws_ticket_store`、
`POST /api/v1/auth/session|ws-ticket`、`GET /me`、`DELETE /session`。

## 不变量

1. 会话 id 用 `secrets.token_urlsafe`，**绝不**从用户数据派生；否则会话可被预测。
2. cookie 是 HttpOnly（+ SameSite），生产环境必须 `secure`（`BR_SESSION_COOKIE_SECURE`）。
3. WS 票据一次性：消费即删除，Redis 端用 Lua 保证原子（Redis 6.0 没有 GETDEL）；票能被复用 = 认证绕过。
4. 未认证访问受保护端点 → 401；别人的资源 → 404（不泄露存在性）。

## 已知陷阱

- 占位实现会一直"看起来没事"：`UnimplementedWsTicketStore` 直接抛错挂了三期，靠静态盘点才发现（M4 P1）。
  到期该落地的占位要么落地要么删掉。
- 票据 TTL 很短（30s）：前端必须在拿到票据后**立即**建 WS，否则 4401（M4 调试时踩过）。
- Redis 不可达时测试用内存实现（`environment=test`），别在单测里连真 Redis——只有分布式用例才需要。

## 测试地图

`tests/test_identity.py`、`tests/test_ws_ticket.py`、`tests/test_media_ws.py`（票的失败路径）。

## 常见变更配方

加一个受保护端点：`Depends(current_principal)` → 归属校验 → 404 语义 → 用例（401 + 404 两条）。
