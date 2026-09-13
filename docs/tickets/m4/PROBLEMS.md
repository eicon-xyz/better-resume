# M4 实现问题记录（PROBLEMS）

> 你点名要求："注意记录过程中遇到的难题，解决的办法"。这里是**只记真事**的台账：
> 每条 = 症状 / 根因 / 修法 / 证据；包含"发现了但决定不修"的项（标注**已知限制**）。
> 实现过程中即时追加，M4-T11 收口时复核。

## 索引

| # | 发现于 | 一句话 | 状态 |
| --- | --- | --- | --- |
| P0 | 提案阶段（环境核查） | 本机无讯飞凭据 → 真机路径不可验证，只能契约级 + 假 adapter | 已知限制（T10 待凭据） |
| P1 | 提案阶段（读代码） | `identity/tickets.py` 仍是 M0 占位（raise NotImplementedError），D11 的一次性票据没落地 | 待实现（T3） |

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

