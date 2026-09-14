# http

## 职责

路由与协议边界（REST / SSE / WS）、错误映射、中间件（request id、实例 id、限流）。

## 对外接口

各 `router`、`gateway_for(request, scene, model_ref)`、`RateLimitMiddleware`、`InstanceIdMiddleware`。

## 不变量

1. 业务异常 → 明确状态码：404（归属）/409（状态冲突）/422（非法转移）/503（熔断、未配置）/504（超时）；
   绝不把供应商异常当 500。
2. 每个响应带 `X-Request-Id` 与 `X-Instance-Id`（后者是 kill-instance drill 的证据）。
3. 限流 fail-open：中间件自身出错不能变成 500。
4. `/healthz` 免鉴权、免限流；业务端点挂在 `/api/v1`。
5. 场景解析只发生在 HTTP 层（`gateway_for`），服务层只接收 gateway。

## 已知陷阱

- 错误分类会在最外层被静默降级：韧性四态没进 `ChatErrorEvent.kind` 的 Literal，兜底 `except` 把类型错误
  伪装成 `unknown`（M3 P8）——改错误映射前先看那个 Literal 与契约用例。
- SSE 必须"生产者 task + 队列"分离，否则心跳超时会取消模型流（M1）。
- 星云/OpenAI 的鉴权失败要在最外层变成 503，不要静默换供应商（M5）。
- 中间件顺序：request id 在最外层（`add_middleware` 是前插，顺序与直觉相反）。

## 测试地图

`tests/test_*_api.py`、`tests/test_ratelimit_http.py`、`tests/test_scene_routing.py`、`tests/test_instance_header.py`。

## 常见变更配方

加端点：Pydantic 入参/出参 → 场景解析 → 服务调用 → 错误映射 → 重生成 openapi/TS → 用例（含 401/404）。
