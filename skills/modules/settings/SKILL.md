# settings

## 职责

唯一的配置入口（pydantic-settings），把环境变量变成有类型的 `Settings`。

## 对外接口

`get_settings()`（lru_cache）、`Settings` 与嵌套块 `ResilienceSettings` / `RateLimitSettings` / `MediaSettings`。

## 不变量

1. 所有变量前缀 `BR_`；嵌套块用双下划线（`BR_RESILIENCE__BREAKER_WINDOW`）；写错前缀 = 配置静默失效、跑的还是默认值。
2. **密钥永远只从环境变量读**，配置里只存"变量名"或空串；任何真实 key 进仓库都算事故。
3. 默认值必须让"本地裸跑"能启动（除了供应商 key），否则 CI 与新人第一步就卡住。

## 已知陷阱

- `get_settings()` 有缓存：测试里改环境变量必须 `get_settings.cache_clear()`（见 `tests/conftest.py` 的 hermetic fixture）。
- 嵌套模型字段名重复会踩 M4 P8（补丁把 tts 预算打进 `MediaSettings`，policy 读不到 → 78 例齐红）：
  加字段时确认加在**正确的类**上。
- `.env` 只在本地存在且被 gitignore；CI 靠 environment 变量。

## 测试地图

`tests/test_settings.py`（默认值、校验失败、嵌套覆盖）、`tests/conftest.py`（隔离）。

## 常见变更配方

加一个配置项：字段 → 默认值 → 在 `Settings` 文档字符串或 README 里写一行 → `tests/test_settings.py` 加断言。
