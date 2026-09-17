# P3 阶段问题台账

| 编号 | 一句话 | 修法 | 测试/证据 |
| --- | --- | --- | --- |
| P34 | **百炼应用调用的带内错误被当成"空成功"**：供应商用 HTTP 200 + `event:error` 帧报错（真机实测 `InvalidParameter: Required parameter(AppId) missing or invalid`），修复前 adapter 只取 `data:` 里的 `output.text`，于是返回 `content=""` + `Done(finish_reason="stop")`——用户看到一个空白回答，而不是"绑定配错了"。真机第一次跑就是这个形状，属于"假成功"，比报错更难查 | 解析帧前的 `:HTTP_STATUS/<n>` 注释作为有效状态；`data:` 帧里出现 `code` 即抛 `LlmVendorError`（4xx 不可重试、5xx 可重试），半截文本也一并失败 | 红：`test_in_band_error_frames_are_not_empty_successes` / `…_server_errors_stay_retryable` / `…_error_after_partial_text_still_fails` → 绿 `tests/llm_gateway/` 86 passed；真机复验 `PROBE_EXIT=3`（EVIDENCE §1.4） |

教训：**"HTTP 200"不等于成功**——SSE 供应商会把失败放进帧里；适配器的默认立场应当是"没拿到 output 就是失败"，
而不是"没拿到 output 就是空答案"。真机第一次跑就抓到了契约套件（假服务端永远回 200 + 正常帧）**测不到**的形状。
