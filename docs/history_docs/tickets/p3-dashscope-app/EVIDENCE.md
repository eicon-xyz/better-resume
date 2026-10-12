# P3 真机证据（百炼应用调用 = 星云的阿里等价物）

- 日期：2026-09-17；分支 `p3/dashscope-evidence`（基于 main `a30aac8`，P3-B 已合并进 main）
- **结论：代码面已验证（契约套件 10 条 × 3 实现 + 假 SSE 服务端）；真机调用一次都没成功**——
  供应商对给定 app_id 一律回 `InvalidParameter: Required parameter(AppId) missing or invalid`
  （主域名与工作区域名返回逐字节相同的错误）。**未验证就写未验证：这条链路目前没有成功的真机回答。**
- 真机花费：本次 **6 次**（P1 人工记账 ~185 → **~191 / 200**）。全部是错误响应，未返回 usage（无计费证据）。

## 1. 真机做了什么（原始输出）

### 1.1 零成本连通性预检（不算调用）
`@text
dashscope.aliyuncs.com -> 401 (tls_verify=0)
issuer=C = BE, O = GlobalSign nv-sa, CN = GlobalSign GCC R46 OV TLS CA 2025 / subject CN = *.aliyuncs.com
`@
→ 端点真实可达，证书是阿里真证书（**没有**被本机 Watt Toolkit 中间人拦），401 = 缺凭据。

### 1.2 探针 `--schema`（2 次调用，**修复前**）
`@json
{"app_id": "359e0b4f…", "base_url": "https://dashscope.aliyuncs.com", "adapter": "dashscope_app",
 "structured": false, "deltas": 0, "chars": 0, "first_delta_ms": null, "total_ms": 384.6,
 "finish_reason": "stop", "usage_raw": null, "text_head": ""}
{"app_id": "359e0b4f…", "adapter": "dashscope_app", "structured": true, "deltas": 0, "chars": 0,
 "first_delta_ms": null, "total_ms": 341.5, "finish_reason": "stop", "usage_raw": null,
 "text_head": "", "schema_ok": false,
 "schema_error": "response is not valid JSON: Expecting value: line 1 column 1 (char 0)"}
`@
**这两个"空成功"本身就是线索**：HTTP 200、finish_reason=stop、零文本零 usage——不像模型答空，像被吞掉了错误。

### 1.3 原始报文校准（3 次调用：主域名 / 工作区域名 / 主域名复核）
`@text
HTTP/2 200
content-type: text/event-stream;charset=UTF-8
x-dashscope-finished: true
x-request-id: d18bb1bc-3e36-90c4-8ec5-9f8513302004

id:1
event:error
:HTTP_STATUS/400
data:{"code":"InvalidParameter","message":"Required parameter(AppId) missing or invalid, please check the request parameters.","request_id":"d18bb1bc-…"}
`@
工作区域名（实时 ASR 用的那个 `ws-…cn-beijing.maas.aliyuncs.com`）返回**逐字节相同**的帧；
把 app_id 从路径拿掉再打一次，仍是同一条 message——说明**服务端确实没认出这个 app_id**，不是我们拼错了 URL。

### 1.4 修复后复验（1 次调用）
`@json
{"structured": false,
 "error": "dashscope app 359e0b4f… returned InvalidParameter: Required parameter(AppId) missing or invalid, please check the request parameters.",
 "kind": "vendor"}
`@
`PROBE_EXIT=3` —— 错误不再被吞，探针按契约报"结构化/真机失败"。

## 2. 这次真机跑出来的真 bug（已红-绿修复）

**P34（台账见 `PROBLEMS.md`）：带内错误帧被当成空成功。**
供应商用 **HTTP 200 + `event:error` 帧**报错；修复前的 adapter 只认 `data:` 里的 `output.text`，
于是把失败读成"答了个空"，返回 `content=""` + `Done(finish_reason="stop")`——**绑定坏了却给用户一个空白回答**。

| 步骤 | 内容 |
| --- | --- |
| 红 | 3 条新用例：`test_in_band_error_frames_are_not_empty_successes` / `test_in_band_server_errors_stay_retryable` / `test_an_error_after_partial_text_still_fails` |
| 修 | 解析 `:HTTP_STATUS/<n>` 注释作为有效状态；帧里出现 `code` 即抛 `LlmVendorError`（4xx 不可重试 / 5xx 可重试） |
| 绿 | `tests/llm_gateway/` **86 passed**；真机复验见 §1.4 |

## 3. 复跑命令

`@bash
cd '/root/better resume/apps/api' && export PATH="$HOME/.local/bin:$PATH"
uv run pytest tests/llm_gateway/test_dashscope_app_adapter.py            # 15 例（含 3 条带内错误）
uv run python scripts/dashscope_app_probe.py --dry-run                   # 零成本：清单 + 预算
uv run python scripts/dashscope_app_probe.py --schema                    # 2 次调用（真机）
`@

## 4. 未验证项（诚实清单）

1. **应用调用从未成功**：给定 app_id 在两种端点下都被判 `AppId missing or invalid`。需要你确认：
   应用是否**已创建并发布**、app_id 是否取自应用的"应用 ID"、该应用与这把 `BR_DASHSCOPE_API_KEY` 是否同一账号/业务空间。
2. **结构化输出边界**（云端应用能否满足 Pydantic 契约）：未测——必须先有一次成功调用。
3. **增量时序 / 首帧延迟 / usage 有无**：未测（同上；注意：真机始终没返回 usage，连错误响应也没有）。
4. **`session_id` 多轮续聊**：未测。
5. 讯飞星云原生 adapter 真机：与 P1-C 一样仍未验证（无凭据）——本票只是"阿里等价物"。

## 5. 与提案的偏差

| 偏差 | 原因 | 影响 |
| --- | --- | --- |
| 计划 1–2 次调用，实际 **6 次** | 首次结果是"空成功"，按 P25/P27 的教训**必须先校准证据工具**再下结论，于是追加了原始报文与第二域名探测 | 仍在 200 封顶内（~191）；多花的 4 次换来一个真 bug 的修复 |
| 真机结论从"验证协议映射"变成"发现并修掉一个真 bug + 报告账号侧阻塞" | 实测结果，不是预设 | adapter 的错误语义比提案时更硬（带内错误不再静默） |
