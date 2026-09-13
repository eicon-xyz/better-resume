# M4 实现问题记录（PROBLEMS）

> 你点名要求："注意记录过程中遇到的难题，解决的办法"。这里是**只记真事**的台账：
> 每条 = 症状 / 根因 / 修法 / 证据；包含"发现了但决定不修"的项（标注**已知限制**）。
> 实现过程中即时追加，M4-T11 收口时复核。

## 索引

| # | 发现于 | 一句话 | 状态 |
| --- | --- | --- | --- |
| P0 | 提案阶段（环境核查） | 本机无讯飞凭据 → 真机路径不可验证，只能契约级 + 假 adapter | 已知限制（T10 待凭据） |
| P1 | 提案阶段（读代码） | `identity/tickets.py` 仍是 M0 占位（raise NotImplementedError），D11 的一次性票据没落地 | 待实现（T3） |
| P2 | T1 实现 | 尾缀合并把单字重叠当重复：今天 + 天气不错 → 今天气不错（吃掉了正文） | 已修（MIN_OVERLAP=2） |
| P3 | T2 实现 | 供应商“干净关闭”不计入重连次数 + 每次连上都重置预算 → 无限重连 | 已修 |
| P4 | T2 实现 | 接收循环的异常丢在 task 里（调用方永远等不到失败）→ 加 failure + wait() | 已修 |
| P5 | T3 实现 | M0 的通道草图（start/feed/stop）无法表达“通道结束/失败” → 协议补 wait() | 已修（协议扩展） |
| P6 | T3 实现 | 收尾事件永远发不出去：sender 先被 cancel，stop() 的 final 无人投递 | 已修（先 stop 再 flush） |
| P7 | 全程 | 写 docstring/补丁脚本时反复踩转义（反引号、\n、${}）→ 加源码 hygiene 测试 | 已修（守卫测试） |

---

## P0 — 讯飞 AST 真机不可验证（环境事实）

- **症状**：仓库与机器上都没有 `appId / accessKeyId / accessKeySecret`，真机转写无法执行。
- **根因**：讯飞 AST 是付费云服务，凭据只在用户侧。
- **修法**：协议实现 + 本地假 WS 契约测试（T2）+ 脚本化 adapter 端到端（T9）+ 真机验证票（T10）；
  验收文档区分"契约级证据"与"真机证据"，**未验证项明确标注**。
- **证据**：待 T10；在此之前 ACCEPTANCE 里写"未验证（缺凭据）"。

## P1 — WS 一次性 ticket 仍是占位（M0 遗留）

- **症状（静态发现）**：`identity/tickets.py` 的 `UnimplementedWsTicketStore.issue/consume` 直接抛
  `NotImplementedError("...lands with the WS transport (M1+)")`，而 D11 要求 WS 握手用一次性 ticket。
- **根因**：M1–M3 没有 WS 传输，占位没到期。
- **修法**：T3 落地真实现（Redis 优先 / 内存回退，TTL 30s，consume 原子删除），并补"票复用/过期"用例。
- **证据**：待 T3。


## P2 — 尾缀合并的单字歧义：今天 + 天气不错 被合并成 今天气不错

- **症状**：T1 的 test_append_grows_the_sentence_and_keeps_committed_empty 红：期望 今天天气不错，实得 今天气不错。
- **根因**：旧实现的尾缀合并是为了抵消 ASR **重发重叠音频**造成的重复（例如重发 天气不错）。
  我用「最长后缀 == 前缀」实现时，单字重叠（今天 的尾字 天 == 天气不错 的首字）也被当成重复——
  **中文里单字重叠绝大多数是正文，不是重发**，于是把真实内容吃掉了。
- **修法**：MIN_OVERLAP = 2（只有 ≥2 字的尾部重叠才视为重复），包含关系（你好 ⊂ 你好世界）优先判定；
  常量与理由写进代码注释，测试里保留这条 1 字反例。
- **证据**：tests/media/test_assembler.py 22 例全绿（0.029s）；MIN_OVERLAP 导出供上层复用。

## P3 — 重连策略两个坑：干净关闭不计次 + 连上就重置预算（无限重连）

- **症状**：T2 的 test_reconnect_then_give_up 一直不结束（adapter.failure 永远为空）。
- **根因（两次）**：
  1) 服务端“干净关闭”时 async for 正常结束、不抛异常，我原来的 except 分支根本不会被触发，
     于是既不计入 attempt 也不判失败 —— 循环立刻重连；
  2) 修了 (1) 之后我仍在“连接建立成功”时把 attempt 归零，于是每次连上→被踢→预算复原→再连，
     仍然是无限重连（测试第二次才抓到）。
- **修法**：把“连接结束”（无论异常还是正常关闭）统一当作一次掉线，attempt 只在 start() 时归零；
  预算按“一条通道的生命周期”计，语义写进代码注释。
- **证据**：tests/media/test_xunfei_ast.py::test_reconnect_then_give_up（2 次掉线、1 次重连预算 → AiUnavailable）。

## P4 — 接收循环异常被 task 吞掉：调用方永远等不到失败

- **症状**：vendor 返回错误码（10165）时，WS 端点侧完全无感，客户端只能一直等。
- **根因**：接收循环跑在 create_task 里，异常只留在 task 对象上（甚至只打印 Task exception was never retrieved）。
- **修法**：通道增加 failure 字段与 wait()：接收循环把失败存下来并结束；端点 await wait() 得到失败，
  再用 4411 关闭连接（协议上补一个方法，比在端点里 try/except 更能表达语义）。
- **证据**：test_vendor_error_frame_surfaces_as_unavailable。

## P5 — M0 草图缺 wait()：转写通道的三个方法表达不了“通道结束/失败”

- **症状**：WS 端点 AttributeError: ScriptedTranscriptionChannel has no attribute wait（T3 五个用例齐红）。
- **根因**：§12.2 的草图只有 start/feed/stop，但端点需要一个“通道自己结束或失败”的信号；
  两个 adapter 都没有这个能力。
- **修法**：给 TranscriptionChannel 协议补 wait()（含 docstring 说明为什么），xunfei 适配器 await 接收任务，
  scripted 适配器等一个 Event；占位实现同样补上（保持“缺什么就大声报错”）。
- **证据**：tests/test_media_ws.py 6 例 + tests/media 32 例全绿。

## P6 — 收尾事件永远发不出去（sender 先被 cancel）

- **症状**：test_final_packet_archives_the_sentence 挂死：客户端等不到 final 事件。
- **根因**：端点用 asyncio.wait(FIRST_COMPLETED) 等“谁先结束”，然后立刻 cancel 掉 sender；
  而 final 事件是在 channel.stop() 时才产生的——此时已经没有人在发队列了。
- **修法**：把收尾顺序固定为“先 stop 通道（产生 final）→ 再 flush 队列 → 最后关闭”，
  并把“客户端释放按钮”→ text 帧 {type: stop} 定为显式停止信号（对齐 §7.4 的 stop_transcription）。
- **证据**：同用例现在断言 replace/replace/archive 后收到 final=我负责了订单写入链路的重构。

## P7 — 转义反复踩坑 → 加源码 hygiene 守卫

- **症状**：同一类问题出现三次：M2 的 storage.py docstring 反引号（SyntaxWarning）、
  我自己的 xunfei_ast.py docstring 反引号（又一次 SyntaxWarning）、
  以及用脚本改代码时 TS 模板串与 shell heredoc 的二次转义（Invalid Unicode escape / 字面量 ${copy}）。
- **根因**：非 raw docstring 里的 \` 只在“重新编译”时报 SyntaxWarning（本地 .pyc 缓存会掩盖）；
  补丁脚本里写 \n、${}、反引号时很容易被外层语言先解释一次。
- **修法**：新增 tests/test_source_hygiene.py：用 warnings 捕获逐个 compile 源码文件，
  任何 SyntaxWarning 直接判失败；补丁脚本一律用 chr(10)/chr(36) 构造特殊字符（写进本文件，供后续会话照做）。
- **证据**：tests/test_source_hygiene.py 通过；此后新增/修改的模块不再出现该告警。
