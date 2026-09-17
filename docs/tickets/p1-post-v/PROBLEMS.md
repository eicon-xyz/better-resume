# P1 阶段问题台账

| 编号 | 一句话 | 修法 | 测试/证据 |
| --- | --- | --- | --- |
| P24 | `websockets` 库 `close_timeout` 默认 **10s**：供应商收到 finish-task 后立即回 task-finished，但**不回 WS 关闭帧**，`close()` 挂满 10s——松手→final 10.1s，差点把"能实时"的产品做成"松手后干等 10 秒" | `open_connection` 显式 `close_timeout=1`；另加尾部预算（`finish_timeout_seconds=2s`，预算耗尽仍发 final、不报错——文本已完整，供应商收尾慢不该惩罚用户） | `test_real_connection_bounds_the_close_timeout` + `test_stuck_vendor_tail_is_bounded_and_still_clean` + `test_tail_budget_still_delivers_the_final_text`；端到端对照 15.63s → 6.62s |
| P25 | `v3_ws_probe.py` 原来**发完才收**：websockets 客户端会缓冲服务器帧，9 个增量的时间戳全部塌缩到收帧时刻（5.55s），差点把正确实现误判为"不增量" | 探针改为并发 reader（边发边收），时间戳才是真实到达时间 | 修复前后输出对照（P1-A-EVIDENCE.md §3 c/d） |

| P26 | **worker 在主从切换时 exit 1**：心跳写 `client.set` 位于 `serve()` 兜底 try **之外**，Redis 抖动抛出的 `TimeoutError` 逃出循环；容器无重启策略 → 后台任务永久停摆（M6 P9 只覆盖了阻塞读路径） | 把 `beat` 移进兜底 try：记录 `worker_loop_error` + 退避重试，与 job 循环同一套处理 | 红：`test_serve_survives_a_redis_timeout_in_the_heartbeat`（`assert 1 >= 2`）；真机复跑切换演练：worker_health=healthy + 7 条降级日志（P1-D-EVIDENCE §3/§4） |
| P27 | **演练探针自身的两个缺陷**：① 分区前没登录 → 采到 401 并一度误判 P17 契约被破坏；② 采样调用没有 try/except、恢复没放 finally → 一次 ReadTimeout 让演练崩溃并**把栈留在断网状态** | 分区前先建会话；采样包 try/except；恢复放 `finally`（分区与切换都是） | 原始 curl 对照 503+`retry-after: 5`；崩溃后手动恢复并复跑通过（P1-D-EVIDENCE §1/§2） |

| P28 | **实时 partial 走了批量时代的追加合并**：录音中手打会字乱。`onTranscript` 对**每一个**累积 partial 调 `mergeTranscript`（P23 为「每次松手出一整段」设计）——实时下既不匹配前缀也不匹配包含 → 反复**追加**增长中的整段，与用户打字交错 | `transcriptStore` 新增 `replaceTranscript`：转写只替换**自己上一轮贡献的 span**（span 外的手写全保留；供应商纠错=整段替换；span 被用户编辑过则 no-op+notice，绝不破坏手写；首次贡献沿用 P23 追加规则）；两页各持 `transcriptSpanRef`，点「开始录音」时归零 | 7 条新用例（span 增长/环绕打字/纠错/坏 span 冻结/快速 partial+打字交错）；前端 **168** 全绿；nginx 已重建待复测 |

| P29 | **部署后浏览器还在跑上一版 bundle**：nginx 对 index.html 不发任何 Cache-Control → 浏览器启发式缓存 HTML。P28 修好并重建镜像后，用户复测仍逐字节出现旧症状（「我父我负责我负责过核…」正是旧 mergeTranscript 反复追加的签名）；且页面级测试只喂过 2 个事件，实时多 partial 从未被测到——测试缝缺口同时掩盖了它 | 部署面：index.html 发 `no-store`、内容哈希的 /assets/ 发 `public, immutable`；compose_smoke 新增两条响应头断言；补页面级回归（用用户报障原文的 partial 序列，旧代码必挂、新代码通过） | compose_smoke PASS×2；VoiceWiring 新增 2 例（前端 170 全绿）；nginx 重建后 curl -sI 实测头 |

| P30 | P28 修完仍复发（用户第二轮报障「我好好，我是来…」）：**chat 的 Composer 是第三个合并层**——它持有自己的输入框状态，内部还在用 mergeTranscript；上轮只改了页面级 onTranscript，且既有测试全从 store 事件驱动，从未测过「transcript prop 逐事件变化」这条组件内部路径 | Composer 改用 replaceTranscript + 组件内 spanRef（transcript 变空/发送清空框时归零）；全仓 mergeTranscript 调用点清零 | 新增 Composer.test.tsx 3 例（红 2：增长/纠错序列、纠错时保留手写；绿后 173 全绿）；教训：**改合并语义必须清点全部调用层**，测试缝要覆盖「prop 驱动的组件内部合并」 |

| P31 | **`verify.sh --layer all` 静默漏掉 contract 层**：`--list` 与 AGENTS.md 都写「all = unit + contract + scripts」，但 `all)` 只展开 unit+scripts；`tests/test_verify_script.py` 也只断言 `--list` 里出现层名，没钉 `all` 的展开 → 本地"收口"永远不跑 ruff/eslint/tsc/alembic/契约三件套，**M6 P16 那个失败模式原地复活**（PR #8 上暴露：本地"全绿"、CI 直接红） | 抽出 `add_api_contract` / `add_web_contract` / `add_scripts` 复用，`all)` 逐层调用各层自己的 builder（标签与展开共用一个定义） | 红：`test_all_layer_actually_runs_unit_contract_and_scripts` 列出被跳过的 9 条 contract 命令 → 绿（`test_verify_script.py` 4 passed） |

| P32 | **fixture 断言不 hermetic**：`test_fixture_audio_check_passes_on_the_pinned_file` 断言 `data/audio/p1c-multi-sentence-16k.wav` 存在——但 `data/` 是 gitignored（Q3：不入库 wav）→ 干净 checkout 必红（CI 实测 743 passed / 1 failed），本机因文件在才绿 | 单测只留 hermetic 的「缺失即拒绝」（tmp 路径）；把「存在 + pin 一致」挪到真正需要它的 **real 层预检**：缺文件或字节漂移都在**花钱之前** exit 2（`VERIFY_FIXTURE_AUDIO_DIR` 可覆盖，测试才 hermetic） | 红：`test_real_layer_refuses_when_the_fixture_audio_is_absent` / `..._pinned_fixture_drifted`（当时只报 "needs the compose stack"）→ 绿；本地真 fixture sha256 = pin `8bcd67…`（`make_fixture_audio.py --check` exit 0） |

| P33 | **`fault_probe.py` 过不了全仓 `ruff format --check .`**：P1-D 提交 2f394be 里多行 `client.get(...)` 可折叠成一行；P1 收口写的"静态检查干净"只查了**改动文件**，而 CI contract 步查全仓 → P32 修完这里会接着红 | `uv run ruff format scripts/fault_probe.py`（纯格式，无语义变化） | `--layer contract` **9/9 绿**（ruff check/format、alembic upgrade/check、openapi check、api-index check、eslint、tsc、check:api） |

教训：**close() 也是一次网络等待**——所有连接参数（open/ Close/代理）都必须显式化，不能信库默认值；
**e2e 探针的收发时序本身会撒谎**，证据工具要先于结论被校准。
**收口脚本自己的「标签 vs 展开」也会漂移**（P31）：本地收口必须跑「与 CI 同一条命令」，而不是「我以为它跑了」——
`--list` 写着 contract 不代表 `all` 会跑 contract，这次靠回归测试把两者钉在一起才收口。
**测试里不许出现「我这台机器上恰好有的文件」**（P32）：本机绿、干净 checkout 红，是 hermetic 纪律（P15）的正面案例。
