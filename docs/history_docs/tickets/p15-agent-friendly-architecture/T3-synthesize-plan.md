# T3 综合重构计划，落入 README 六段

Type: task
Status: resolved
Blocked by: T1, T2
执行方: lead（制定计划不外派）
唯一写入路径: `docs/tickets/p15-agent-friendly-architecture/README.md`

- 输入：`recall-report.md`（F 条目）、`pitfalls-report.md`（P 条目）、correct 修复阶梯、architect 设计红旗清单。
- 计划行文用 `建议：` 开头；每条必须带 `[F..]` 或 `[P..]` 引证，无数据支撑的建议删掉。
- 候选形态逐个过 `architect/references/design-red-flags.md` 筛查，结论写进该条建议。
- 开放设计问题用 prototype 原型回答，结论写进 README，不问用户。
- 验收：`grep '^建议：' README.md | grep -c '\[F[0-9]\|\[P[0-9]'` 等于 `grep -c '^建议：' README.md`，且建议条数 ≥ 5。
## Answer

15 条实施建议（分三层）已落入 README.md「范围」节，每条带 [F../P..] 引证与红旗筛查结论；三个开放问题由原型探针回答（结论在 README「原型结论」节）。实施待用户点头。
