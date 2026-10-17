# T17 审计引证重锚与 scripts 层收口（AGENTS.md：改过被引用文件后引证要重锚）

Type: task
Status: resolved
Blocked by: T12, T13, T14
唯一写入路径: `docs/audit/units/`（红线内：只重锚引证行号/范围，不改结论）

## 五栏

- 范围：T12/T13/T14 落地后的 `apps/api/src/better_resume/**`（llm_gateway/interview_engine/media 被重构或修正过的文件）、`docs/audit/units/*.json`、`scripts/verify_audit_evidence.py` 的口径（docs/audit/CONTRACT.md）。
- 唯一写入路径：`docs/audit/units/` 内引证锚点（文件:行号或范围）；T17-EVIDENCE.md 仅两段自述。
- 验收口径（原始输出贴进 T17-EVIDENCE.md）：
  1. `uv run python scripts/verify_audit_evidence.py --strict` 读数恢复全绿（以 HEAD b09bbd2 的基线读数 verifiable 122 / partial 0 / 0 problem 为参照，允许条目数随重构微调但 partial/problem 必须 0）；
  2. 层内既有 pytest 审计用例（test_every_audit_citation_is_corroborated_by_its_evidence）绿；
  3. `bash scripts/verify.sh --layer scripts` 退出 0（四门禁 + 既有 audit 两行全绿，这是 T8 接线的最终收口读数）；
  4. 权威全量 pytest 在**新鲜隔离库**（如 `br_p17_verify`，自建并迁移）上串行复跑绿（读数看 junitxml；共享库会被并行/残留污染，见 PROBLEMS.md P15-1）。
- 红线：只改引证锚点（行号/范围/文件路径）；对确已被本轮重构修复的 issue，按 `docs/audit/CONTRACT.md` 记 `fix_record`（带证据指针，如 http-06 引的 `_invalidate_hot` 已被 T13 删除）——除此之外不改审计结论、不动 issue 描述；不动代码；不 commit/push/开 PR。
- 不接受的自由度：不许为绿而删引证或改判定口径（D22：判定必须真判定）；不许把行号改成范围去「兼容漂移」而内容对不上（逐字级 --strict 会抓）；发现代码与审计结论真的不一致时停下来报，不许两边各改一点。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T17-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

16 条引证重锚 + 5 处证据摘录刷新 + http-06 记 fix_record；`--strict` 122/0/0、审计用例绿、`--layer scripts` 12/12 退出 0、隔离库权威全量 1009/0/0/0。

### 追记（出票方验收）

- 复跑 `--strict` 122/0/0 退出 0；变异演示：把一条锚点挪到文件外的虚构行段（样本值见 T17-EVIDENCE）→ LG-06 判 PART+STRUCT 退出 1，恢复逐字节一致。（注：此处不写引证形状文本——引证门禁连出票方的示例都判，已实测。）
- LG-06 裁决：另立 T20 把 `build_for_model` 收进工厂协议、清 getattr 私约；`fix_record` 等真修完由 T20 记（半修不记 fixed/fixing，保持诚实）。
- 标题内嵌旧行号/计数保留原样（issue 描述红线），语义复核遗留记 P15-7。
- MODULE-AUDIT.html 重建并入收口清理（派生产物，非本票面）。
