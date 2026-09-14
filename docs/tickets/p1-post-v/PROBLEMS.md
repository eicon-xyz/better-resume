# P1 阶段问题台账

| 编号 | 一句话 | 修法 | 测试/证据 |
| --- | --- | --- | --- |
| P24 | `websockets` 库 `close_timeout` 默认 **10s**：供应商收到 finish-task 后立即回 task-finished，但**不回 WS 关闭帧**，`close()` 挂满 10s——松手→final 10.1s，差点把"能实时"的产品做成"松手后干等 10 秒" | `open_connection` 显式 `close_timeout=1`；另加尾部预算（`finish_timeout_seconds=2s`，预算耗尽仍发 final、不报错——文本已完整，供应商收尾慢不该惩罚用户） | `test_real_connection_bounds_the_close_timeout` + `test_stuck_vendor_tail_is_bounded_and_still_clean` + `test_tail_budget_still_delivers_the_final_text`；端到端对照 15.63s → 6.62s |
| P25 | `v3_ws_probe.py` 原来**发完才收**：websockets 客户端会缓冲服务器帧，9 个增量的时间戳全部塌缩到收帧时刻（5.55s），差点把正确实现误判为"不增量" | 探针改为并发 reader（边发边收），时间戳才是真实到达时间 | 修复前后输出对照（P1-A-EVIDENCE.md §3 c/d） |

教训：**close() 也是一次网络等待**——所有连接参数（open/ Close/代理）都必须显式化，不能信库默认值；
**e2e 探针的收发时序本身会撒谎**，证据工具要先于结论被校准。
