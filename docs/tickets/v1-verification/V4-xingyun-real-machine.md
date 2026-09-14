# V4 — 第二家真机：火山方舟（Ark）为主，星辰为备选

- blocking：**火山方舟控制台需先"开通模型服务"**（当前 key 有效但 0 个模型已激活，见下）
- 纪律：**拒绝别名回退**——真机字段与显式映射不符就是 bug，不许加"多别名兜底"蒙混；
  证据里写明实际用的是哪家，不用别家的结果冒充

## 背景（2026-09-14 预检结果）

| 检查 | 结果 |
| --- | --- |
| `GET https://ark.cn-beijing.volces.com/api/v3/models` | **200**（key 有效），列出 40 个可选模型 + 22 个 retiring + 69 个 shutdown |
| `POST /chat/completions`（deepseek-v4-flash-ga-260731 / doubao-seed-2-1-pro-260628 / deepseek-v4-pro-260425） | **404 `ModelNotOpen`**：`Your account 2102002817 has not activated the model … Please activate the model service in the Ark Console` |

即：**key 能用，但账号还没开通任何模型服务**。需要用户操作：火山方舟控制台 <https://console.volcengine.com/ark>
→ 「模型广场 / 开通管理」→ 选择模型 → **开通服务**（Ark 支持直接用 model id 调用；若用「推理接入点」则
拿到 `ep-xxxxxxxx` 作为 model id，两者都可以填进 `ai_models.model_id`）。

## 目标

1. **零代码**把第二家平台接进来：`ai_models` 插一行（`base_url=https://ark.cn-beijing.volces.com/api/v3`、
   `api_key_env=BR_ARK_API_KEY`）→ `PUT /api/v1/scenes/{scene}` 把某个场景指过去 → 下一次 AI 调用即生效；
2. 在真机跑 **M5 的 10 条 vendor 无关契约**（同一套用例 × 第二个真后端）+ 一次完整面试流程；
3. 与官方 DeepSeek 做**同 prompt 对照**（同一个 `OpenAICompatAdapter` 代码路径，只是 base_url/model 不同），
   证明"换平台不发版"不是纸面话；
4. 若星辰（`XINGCHEN_API_KEY/SECRET` + flow_id）也能拿到，作为**第三家/真·第二 adapter** 追加验证；
   拿不到就注明"环境不具备"，不算失败。

## 交付物

- `docs/tickets/v1-verification/V4-EVIDENCE.md`：
  - 鉴权与模型列表（脱敏）、场景绑定切换前后各一次真机调用摘要（model / usage / 耗时）
  - 10 条契约用例在 Ark 上的结果（同一套断言，失败就写失败）
  - 与 DeepSeek 的字段集合差异表（只记录，不自动兼容）
  - 错误面：错 key → 401/403；未开通模型 → 404 `ModelNotOpen`（**已经在预检里抓到**）；限流 → 429 行为
- `apps/api/scripts/adapter_smoke.py`：`--real-ark`（或把现有契约模式参数化）——用真实 base_url + key 跑同一套断言
- 若星辰可用：同一个 `V4-EVIDENCE.md` 追加一节，**不改**现有 `XingyunWorkflowAdapter`

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 平台接入 | 插一行 + 改绑定即可用；**没有为 Ark 改动业务代码**（diff 仅 SQL/环境变量） |
| 四链路 | 出题 / 评分 / 追问 / 总结 在 Ark 上全部通过 Pydantic 校验（`response_format: json_object` 若被拒，靠提示词 + 重试也要过） |
| SSE 归一 | 事件类型只出现 `ContentDelta/ReasoningDelta/VendorMeta/Done` |
| 契约 | M5 的 10 条用例在 Ark 上全绿；失败项如实记录 |
| 错误面 | 未开通模型 → 404 `ModelNotOpen`；错 key → 401/403；两者的 503/502 映射与文档一致 |
| 对照 | 与 DeepSeek 的差异表 ≤1 页，每条给出"接受/拒绝"结论 |

## 不做

- 不把默认供应商从 DeepSeek 换掉；不做 Ark 侧参数调优；不引入第三家托管编排（星辰除外，作为备选）。

## 预估

用户开通模型后 **0.5 会话**（零代码）；若追加星辰真机则再 +1 会话。
