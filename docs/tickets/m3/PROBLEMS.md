# M3 实现问题记录（PROBLEMS）

> 用途：你点名要求"实现过程中遇到的问题要记录下来"。这里是**只记真事**的台账：
> 每个条目 = 症状 / 根因 / 修法 / 证据；包含"发现了但决定不修"的项（标注为**已知偏差**）。
> 条目在实现过程中即时追加，M3-T10 收口时在此复核。

## 索引

| # | 发现于 | 一句话 | 状态 |
| --- | --- | --- | --- |
| P0 | 提案阶段（读代码） | M2 遗留：四个 resilience key 里有三个不满足去重语义前提（回放一开就串号） | 待修（T8） |

---

## P0 — resilience key 不满足去重语义前提（M2 遗留）

- **症状（静态发现）**：question_service.build_generation_key 只含 session + 姓名/邮箱；
  follow_up_service 的 key 只有 followup\|{session}\|{question_no}（不含答案摘要）；
  report_service 只有 report\|{session}；chat/service.build_resilience_key 不含 model_ref。
- **根因**：M1/M2 的 resilience 是直通实现（DirectAiResilience），key 只是"占位传参"，
  没有测试证明 key 能区分输入；而 §4.1.5 的 key 家族要求 stage|sessionId|questionNumber|sha256(payload)。
- **为什么现在必须修**：M3 打开回放后，"不同输入命中同一 key"不再只是浪费，
  而是**返回错误结果**（换简历出题命中旧批次、换答案复用旧追问、换模型串流）。
- **修法**：T8 把四个 key 收敛成显式纯函数并单测（同输入同 key / 换任一维度 key 必变 / key 不含原文）。
- **证据**：待 T8 测试输出。

