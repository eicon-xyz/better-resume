# T22 收口重锚与渲染产物重建（全代码票落定后的最后清理）

Type: task
Status: resolved
Blocked by: T16, T18, T19, T21, T23, T24, T25, T26
唯一写入路径: `docs/audit/units/` 与 `docs/audit/MODULE-AUDIT.html`

## 五栏

- 范围：全部代码票落定后的 `docs/audit/units/*.json` 引证新鲜度（重点 LG-07/LG-09 及 T16/T19 移位波及项）、`scripts/verify_audit_evidence.py --strict` 读数、`docs/audit/` 的生成脚本（CONTRACT.md 口径）。
- 唯一写入路径：`docs/audit/units/`（锚点与必要时的 fix_record）与 `docs/audit/MODULE-AUDIT.html`（生成脚本重建，不手改）。
- 验收口径（原始输出贴进 T22-EVIDENCE.md）：
  1. `uv run --project apps/api python scripts/verify_audit_evidence.py --strict` → partial 0 / problem 0 / unverifiable 0；
  2. 341± 量级的引证抽样语义复核 ≥30 条（含 P15-7 点名的弱匹配窗口 LG-09），逐条给「窗口内容与断言相符」的短判词；
  3. `bash scripts/verify.sh --layer scripts` 退出 0；隔离库权威全量 pytest 绿（出票方终验复跑）；
  4. `MODULE-AUDIT.html` 由生成脚本重建，读数（units/issues/citations 计数）与 units 一致。
- 红线：不改审计结论与 issue 描述（确已修复的才记 fix_record）；不改代码；不 commit/push/开 PR。
- 不接受的自由度：不许为绿放宽弱匹配（那是 P15-7 的工具强化票，不在本票）；抽样必须含弱行窗口，不许只抽强引证；HTML 不许手改。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T22-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

引证重锚：strict 由 118/2/2 转 122/0/0（含 6 条未报红但错指的一并修正），38 条语义抽样含 LG-09 弱窗口；MODULE-AUDIT.html 由生成脚本重建；--layer scripts 16/16 退出 0；隔离库全量 1018/0/0/0。

### 追记（出票方验收）

- 复跑 strict 122/0/0；变异演示：LG-09 锚点挪出文件 → PART+STRUCT 退出 1，恢复逐字节一致。
- --layer scripts 复跑 ALL PASS (16 commands) 退出 0——四门禁 + 审计链 + 派生产物自此常驻同一命令。
- 三条偏差（多修 6 条、53-61 之差按实况 54-62、窄锚不放宽）全部采纳，正是票面要的口径。
