# llm-gateway

## 职责

所有模型调用的唯一接缝。两个 adapter（OpenAI 兼容、星云工作流）+ 模型注册表 + 场景绑定与解析。

## 对外接口

`LlmGateway.complete/stream`、`ChatRequest/ChatResult/StreamEvent`、`ModelRegistry`、
`SceneResolver`、`SceneBindingStore`、`to_xingyun_payload`。

## 不变量

1. 每个调用方只依赖 `LlmGateway`；**服务层不知道供应商**（换供应商 = 改一行绑定）。
2. 结构化输出必须过 Pydantic 强校验；失败先重试一次，仍失败抛 `LlmSchemaError`（不可重试）。
3. **不做别名回退**：缺字段就报错，不让"云端字段改名"变成静默错值（M5 P0，旧项目坏味道#5）。
4. 密钥只按 env 名读取；注入防御（`firewall`）对所有供应商一视同仁。

## 已知陷阱

- 星云只提供 SSE 路径，因此它的 `complete()` 是"收集完再校验"；两层重试会放大调用（M5 的嵌套重试坑）。
- 场景绑定的 `is_configured` 是 **async**（M5 follow-up）：调用处忘了 `await` 会永远判真。
- 星云 payload 的字段形状需要真机验证（M5 P1，本机无凭据未做），本地只有假服务端契约测试。

## 测试地图

`tests/llm_gateway/`（adapter/registry/映射） + `tests/test_adapter_contract.py`（一套 10 条 × 2 实现）
+ `tests/test_scene_routing.py`（端点按场景解析）。

## 常见变更配方

加供应商：实现 `LlmGateway` → 注册 `GatewayFactory` → 加入契约套件的 parametrize → 绑定才能切过去。
