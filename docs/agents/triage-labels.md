# Triage Labels

技能用五个规范角色说话；本文件把它们映射到本仓库 tracker 里实际使用的字符串。

本仓库用**本地 markdown** tracker（`docs/tickets/<stage>/`），所以标签表现为
**票据文件靠近顶部的 `Status:` 行**，不是 GitHub label。

| 规范角色 | 本仓库写法 | 含义 |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | 维护者需要先评估 |
| `needs-info` | `needs-info` | 等报告者补充信息 |
| `ready-for-agent` | `ready-for-agent` | 已完整规格化；**本仓库仍需用户点头才开工**（见 `issue-tracker.md` 的人工闸门） |
| `ready-for-human` | `ready-for-human` | 需要人来实现 |
| `wontfix` | `wontfix` | 不做 |

写法：票据文件靠近顶部一行 `Status: <字符串>`。**没有 `Status:` 行 = 未分类**（等价于未 triage）。

技能提到某个角色时（例如「打上 AFK-ready 标签」），用本表右列对应的字符串。
右列以后若要换成本仓库自己的词表，直接改这张表即可。
