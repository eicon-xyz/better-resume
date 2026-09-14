# P1 阶段问题台账

| 编号 | 一句话 | 修法 | 测试/证据 |
| --- | --- | --- | --- |
| P24 | `websockets` 库 `close_timeout` 默认 **10s**：供应商收到 finish-task 后立即回 task-finished，但**不回 WS 关闭帧**，`close()` 挂满 10s——松手→final 10.1s，差点把"能实时"的产品做成"松手后干等 10 秒" | `open_connection` 显式 `close_timeout=1`；另加尾部预算（`finish_timeout_seconds=2s`，预算耗尽仍发 final、不报错——文本已完整，供应商收尾慢不该惩罚用户） | `test_real_connection_bounds_the_close_timeout` + `test_stuck_vendor_tail_is_bounded_and_still_clean` + `test_tail_budget_still_delivers_the_final_text`；端到端对照 15.63s → 6.62s |
| P25 | `v3_ws_probe.py` 原来**发完才收**：websockets 客户端会缓冲服务器帧，9 个增量的时间戳全部塌缩到收帧时刻（5.55s），差点把正确实现误判为"不增量" | 探针改为并发 reader（边发边收），时间戳才是真实到达时间 | 修复前后输出对照（P1-A-EVIDENCE.md §3 c/d） |

| P26 | **worker 在主从切换时 exit 1**：心跳写 `client.set` 位于 `serve()` 兜底 try **之外**，Redis 抖动抛出的 `TimeoutError` 逃出循环；容器无重启策略 → 后台任务永久停摆（M6 P9 只覆盖了阻塞读路径） | 把 `beat` 移进兜底 try：记录 `worker_loop_error` + 退避重试，与 job 循环同一套处理 | 红：`test_serve_survives_a_redis_timeout_in_the_heartbeat`（`assert 1 >= 2`）；真机复跑切换演练：worker_health=healthy + 7 条降级日志（P1-D-EVIDENCE §3/§4） |
| P27 | **演练探针自身的两个缺陷**：① 分区前没登录 → 采到 401 并一度误判 P17 契约被破坏；② 采样调用没有 try/except、恢复没放 finally → 一次 ReadTimeout 让演练崩溃并**把栈留在断网状态** | 分区前先建会话；采样包 try/except；恢复放 `finally`（分区与切换都是） | 原始 curl 对照 503+`retry-after: 5`；崩溃后手动恢复并复跑通过（P1-D-EVIDENCE §1/§2） |

教训：**close() 也是一次网络等待**——所有连接参数（open/ Close/代理）都必须显式化，不能信库默认值；
**e2e 探针的收发时序本身会撒谎**，证据工具要先于结论被校准。
