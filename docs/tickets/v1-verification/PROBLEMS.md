# V1 验证阶段问题台账

## P17 — Redis 重启窗口内会话接口返回 500（V6 故障注入发现）

- **症状**：`bash scripts/fault_injection_drill.sh` 的 redis-restart 实验里，重启后带旧 cookie 调
  `GET /api/v1/auth/me` 得到 **500**；故障窗口内也混着 `server_error`。期望是 **503 + Retry-After**。
- **根因**：`RedisSessionStore` 直接把 `redis.RedisError` 抛出去，没有映射；FastAPI 只注册了业务异常
  （400/404/409/422/502/503/504），于是连接错误变成未处理异常 → 500。语义上也不对：
  **"查不到会话"是 401（请重新登录），"问不到 Redis"是 503（现在别试，稍后重试）**——
  返回 401 会让客户端去做一件同样会失败的事。
- **修法**（红-绿）：
  1. `identity/store.py` 新增 `SessionBackendUnavailable`；
  2. `RedisSessionStore` 所有命令走一个 `_call()` 缝，把 `redis.RedisError` 翻成该异常；
  3. `main.py` 把它注册到已有的 `_service_unavailable` 处理器（503 + `Retry-After: 5`）。
- **证据**：`tests/test_identity_backend_down.py` 4 例（store 翻译、缺会话仍 401、后端不可用 503+Retry-After）；
  故障注入复跑里 `old cookie after restart: 503`（修前是 500）。
- **教训**：故障注入能发现"单测永远碰不到"的语义错误——**基础设施坏了要报"不可用"，不是报"你未登录"**。

## P18 — 场景绑定缓存是"每进程"的：另一个副本继续用旧绑定（V2 真机压测暴露）

- **症状**：真模型 `chat-sse c=2` 那一轮 24 个请求里 **8 个 503**（错误率 33%），而同一秒里另一个
  api 副本对同一路径返回 **200**。日志里没有 `ai_call_failed`、没有供应商 503、熔断器全 closed。
- **根因**：V1 的失败探针把 `chat` 场景临时绑到无凭据模型（期望 503），随后在 `finally` 里改回
  `deepseek-flash`。但 `PUT /api/v1/scenes/{scene}` 只 `invalidate()` **处理该请求的那个进程**的缓存；
  M5 的 `SceneResolver._bindings` **没有 TTL**，于是另一个副本把 `real-smoke-broken` 一直缓存着，
  之后所有落到它上面的 chat 流请求都按"未配置"返回 503。诊断耗时点：三个副本的日志并排看，
  同一秒 200 vs 503 才能确认是**进程间状态**而不是供应商。
- **修法**（红-绿）：
  1. `SceneResolver` 的缓存条目带时间戳，新增 `cache_ttl_seconds`（默认 5s，0=不缓存）与注入时钟；
  2. `settings.scene_binding_cache_seconds=5.0`，`main.py` 与 `worker.py` 都传进去；
  3. 测试：`tests/llm_gateway/test_scene_binding_propagation.py`（第二个副本在 TTL 内仍用旧绑定、
     超时后收敛；0 TTL 每次读库；`invalidate()` 仍然立即生效）。
- **证据**：
  - 修复前：`chat-sse c=2` → 8×503；修复后同一命令 → **12/12 ok、0×503**（§V2-EVIDENCE）。
  - 线上验证：PUT 把 `chat` 改成 `deepseek-v4-pro` 后，另一副本在 **2.2s** 内开始返回新模型的
    `meta` 帧（TTL=5s 是上界）；恢复绑定同样生效。
- **教训**：**多实例下"进程内缓存 + 只在本地失效"= 配置漂移**。M5 的票据备注里其实写着
  "绑定配置的多实例一致性也在 M6"——M6 漏了，V1/V2 才把它抓出来。凡是"改了要生效"的缓存，
  都要么有 TTL，要么有跨进程失效通道。

## P19 — 流式 usage 没有主动请求：换一家平台就静默丢 token 统计（V4 发现）

- **症状**：V4 第一次跑百炼 \`qwen-plus\`，\`chat-stream\` 步骤拿不到 \`meta\` 帧：
  \`models: []\`、\`total_tokens: 0\`，而同一脚本打 DeepSeek 时一切正常。
- **根因**：OpenAI 兼容协议里流式响应的 \`usage\` 是**可选**的，DeepSeek 默认带、DashScope 默认不带
  （需要请求里给 \`stream_options: {"include_usage": true}\`）。我们从未发送该字段，于是这类平台的
  token 统计与前端 \`event: meta\` 一直为空——**没有任何报错**，只是数字悄悄消失。
- **修法**：按模型行开关（\`extra.stream_usage=true\` → 流式请求带 \`stream_options\`），默认关闭，
  因为不认这个字段的厂商可能直接 400。测试：\`tests/llm_gateway/test_openai_compat.py::
  test_streaming_usage_is_requested_only_when_the_model_row_asks_for_it\`。
- **证据**：修复后同一命令 → \`usage={total_tokens: 70, completion_tokens: 52, prompt_tokens: 18}\`
  （V4-EVIDENCE §2）；这也是"真机 vs 假上游"判定的关键字段（假供应商没有 usage）。
- **教训**：**"可选字段"才是最容易静默丢失的东西**——只要某平台的默认行为与我们的假设不同，
  就没有报错、只有空值。跨平台验证的价值正在这里。
