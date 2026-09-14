# V4 — 星云工作流真机验证

- blocking：无（需要 Q4 的 key/secret + 每场景 flow_id）
- 纪律：**拒绝别名回退**——真机字段与我们的显式映射不符就是 bug，不许加"多别名兜底"蒙混

## 目标

验证 M5 的第二个 adapter 在真机成立：Bearer(apiKey:apiSecret) 鉴权、`flow_id/uid/stream/history/parameters`
请求形状、SSE 归一成与 OpenAI 路径相同的 `StreamEvent`、结构化输出能过 Pydantic 强校验、
错误三态（超时/不可用/非法输出）与 OpenAI 路径一致。

## 交付物

- `apps/api/scripts/adapter_smoke.py` 已有 `--real-xingyun`：补齐
  - 五个场景各跑一次（`--scene` 逐场景），打印：请求摘要（脱敏）、原始 SSE 帧、归一后事件序列、
    校验后的 Pydantic 对象字段
  - 对照模式：同一 prompt 分别打 DeepSeek 与星云，打印字段集合差异（**只记录差异，不做自动兼容**）
- `docs/tickets/v1-verification/V4-EVIDENCE.md`：五场景证据 + 字段映射表 + 差异清单 + 错误面结果
- 未申请到 flow_id 的场景：写"未验证（缺 flow_id）"，不许用假响应顶替

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 鉴权 | 错误 secret → 明确 401/403 且文案可读；正确凭据 → 200 |
| SSE 归一 | 归一后事件类型只出现 `ContentDelta/ReasoningDelta/VendorMeta/Done`，无未知类型泄漏 |
| 结构化输出 | 五个场景的返回全部通过对应 Pydantic 模型（失败即记录，不加别名回退） |
| 对照 | 与 DeepSeek 的字段差异表 ≤1 页，且每条都有"接受/拒绝"结论 |
| 错误三态 | 提供 3 条真机错误证据（超时、5xx、非法 JSON 各一，或说明为何无法构造） |

## 不做

- 不替换默认供应商（默认仍是 DeepSeek）；不做星云侧编排调优；不引入第三家。

## 预估

1 会话（flow_id 申请由你完成）；调用量取决于你的星云配额。
