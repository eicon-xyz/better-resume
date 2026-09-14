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

## P20 — 批量 ASR adapter 的 \`wait()\` 违反协议：socket 在第一帧就断（V3 发现）

- **症状**：WS 路径（nginx → 票据 → 推 PCM）客户端**第一次 send 就收到 1006**；服务端日志只有
  \`WebSocket … [accepted]\` 和 \`connection open\`，**没有任何报错**；直接用 adapter 也"看起来正常"。
- **根因**：\`TranscriptionChannel.wait()\` 的契约是"阻塞到通道结束"。我的批量 adapter 写成
  \`if self.failure: raise\` → **立即返回**。WS 端点用 \`asyncio.wait({sender, receiver, watcher},
  FIRST_COMPLETED)\` 判定结束，于是它把"wait 返回"理解成"通道结束"，立刻取消全部任务、\`stop()\`（此时
  缓冲还是空的）、关闭 socket —— 客户端自然在第一帧就撞上关闭。
- **修法**：\`start()\` 建 \`asyncio.Event\`，\`stop()\` 在 \`finally\` 里 set，\`wait()\` 等它再抛 failure。
  回归测试 \`test_wait_blocks_until_stop_finished\`（先断言 stop 之前 \`wait()\` 未完成）。
- **同一个 adapter 的第二个坑**：\`httpx.AsyncClient(timeout=…)\` 在本机（WSL 导出的裸 IPv6 \`NO_PROXY\`）
  构造即抛 \`InvalidURL: Invalid port: ':1]'\` —— M3 在 LLM adapter 上修过同一个问题，新 adapter 又踩了。
  修法：\`build_client()\` 统一兜底（\`InvalidURL/ValueError\` → \`trust_env=False\`）+ 测试 + 启动日志。
- **教训**：**实现 Protocol 不等于满足契约**。类型检查看不出"wait() 该阻塞"这种语义，只有端到端跑
  才会暴露；新 adapter 一律先跑一次真实链路（而不是只看单测绿）。

## P21 — 成功路径不关 WS 握手，客户端报 1006（V3 发现）

- **症状**：final 文本已经收到，但客户端拿到 \`ConnectionClosedError code=1006\`（异常关闭）；
  浏览器可能据此显示错误或触发重连。
- **根因**：\`/media/transcribe\` 成功路径 flush 完直接 return，没有显式 \`websocket.close()\`，
  底层实现于是丢了 close 帧。
- **修法**：成功路径显式 \`await websocket.close(code=1000)\`（失败路径仍为 4411）。
- **证据**：修复前后同一条 probe：\`code=1006\` → \`ConnectionClosedOK code=1000\`。

## P22 — 浏览器采集节点没接到 destination：真实浏览器可能一帧都不产生（V5 发现）

- **症状**：用户按住/点击「语音输入」说话，服务端收到的片段有时是静音或极短（供应商 400 `{}`），
  有时根本没有音频；而所有单测与我的 Python WS 探针都正常。
- **根因**：`apps/web/src/audio/capture.ts` 只做了 `source.connect(tap)`（或 `source.connect(processor)`），
  **从未把采集节点连到 `context.destination`**。Web Audio 只驱动"能到达 destination 的节点"，
  所以真实浏览器里 `AudioWorkletNode.process()` / `onaudioprocess` 可能永远不触发。
  M4 的单测用假节点手动 `emit()`，把这条最关键的浏览器约束整个绕过去了。
- **修法**：采集节点经一个**零增益 sink** 连到 destination（`sink.gain.value = 0`，不会把麦克风回放到音箱），
  `stop()` 里一并断开；回归测试断言 `processor.connect(sink)`、`sink.connect(destination)`、`gain.value === 0`。
- **教训**：**用假对象替身时，被替身绕过的"平台约束"要在测试里显式断言**（这里的约束是"图要通到 destination"），
  否则单测越绿，越可能掩盖真实浏览器里的静默失败。

## P23 — 合并规则丢掉了批量转写：第一次有字、后面没字（V5 发现）

- **症状**：浏览器手测"第一次出字，之后再怎么按都不出字"；服务端日志显示 4 次都收到真实语音
  （2.5–5.3s、峰值 5.6k–32767）、**供应商零失败**——文本产生了却被前端丢弃。
- **根因**：`mergeTranscript(local, merged)` 是按**增量**厂商的语义写的：只有当输入框为空、
  或 `merged` 是 `local` 的**前缀延伸**时才采纳，否则保留手写内容并**丢弃转写**（防覆盖）。
  我们的批量 ASR（V3）每次松手返回的是**一整段新句子**，永远不是已有草稿的前缀 → 第 2 次起全被丢。
- **修法**（保留"绝不覆盖手写内容"的不变量）：
  1. `local` 为空或 `merged` 是前缀延伸 → 采纳（增量路径不变）；
  2. `local` 已包含 `merged` → 去重，不改（同一次转写重复到达、或用户已在草稿里编辑过）；
  3. 其余情况（新的整段） → **追加** `local + merged`，返回 `notice=true`；
  4. 提示文案从"未自动插入"改为"已保留你写的内容，新的转写追加在后面"。
- **证据**：`apps/web/src/audio/transcriptStore.test.ts` 新增"追加新整段""同一段不重复追加"两例；
  用户手测：连续两次不同句子都能追加显示，手写内容未被覆盖。
- **教训**：**换供应商类型（增量 → 批量）会改变上层合并语义**。"不覆盖用户输入"这个不变量两种语义都能满足，
  但"新内容是替换还是追加"必须在 adapter 之外显式决定，并写进测试与文案。
