# M5-T2 — Resolver + `GET/PUT /api/v1/scenes`

- blocking：M5-T1
- 纪律：先写失败测试（红），再实现（绿）

## 目标

场景 → 具体 gateway 的解析器：读绑定 → 构造对应 adapter（+ 密钥）→ 交给调用点；
并把绑定的查看/切换暴露成受保护的 HTTP 端点（"换供应商不发版"的落地形态）。

## 交付物

- `llm_gateway/resolver.py`：`SceneResolver`
  - `async resolve(scene: LlmScene) -> LlmGateway`：
    - 绑定 `openai_compat`：走现有 `ModelRegistry.resolve(target_ref)` + `build_llm_gateway(spec, key)`
    - 绑定 `xingyun`：走 T3 的 adapter 工厂（apiKey/apiSecret/flow_id）
    - 缺绑定 / 未配置密钥 → **明确错误**（`LlmConfigError`，前端能看到"这个场景还没配好"）
  - 进程内缓存（场景 → 绑定行），带 `invalidate(scene|None)`；PUT 后主动失效
- `http/scenes.py`：
  - `GET /api/v1/scenes`（需登录）：每个场景 `{scene, adapter, target_ref, configured, is_default}`
    —— `configured` 诚实标记（星云缺密钥时为 false，照 D12 的 /models 传统）
  - `PUT /api/v1/scenes/{scene}`（需登录）：`{adapter, target_ref}` → 校验 + upsert + 失效缓存，
    返回同一视图；未知场景 → 404，未知 adapter → 422
- 测试：`tests/llm_gateway/test_resolver.py` + `tests/test_scenes_api.py`（≥12 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 解析 openai_compat | 返回的 gateway 就是注册表那一条（同一 model_ref） |
| 解析 xingyun | 返回星云 adapter（类型断言 + 配置注入正确） |
| 缓存 | 连续两次 resolve 只读一次库（计数断言）；PUT 后重新读 |
| 缺绑定 | 抛 `LlmConfigError`（含场景名） |
| 未配置密钥 | `configured=false`；resolve 时抛明确错误（不静默降级到别的供应商） |
| GET 视图 | 五场景齐全；`is_default` 标记默认绑定 |
| PUT 校验 | 未知场景 404；未知 adapter 422；空 target_ref 422 |
| PUT 生效 | 切换后 GET 反映新绑定，且解析结果随之改变 |
| 鉴权 | 未登录 GET/PUT 都是 401 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway/test_resolver.py tests/test_scenes_api.py` | 全绿 |
| `uv run python scripts/export_openapi.py --check` | 通过（新端点进契约） |

## 不做

- 不做多租户/权限分级（登录即管理员，作品集范围内够用）；
- 不做绑定的热推送（进程内缓存 + 端点显式失效；多实例一致性留 M6）。

