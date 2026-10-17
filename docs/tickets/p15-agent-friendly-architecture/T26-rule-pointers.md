# T26 规则文件改指针（建议 14 的收尾：只引用不复制）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `AGENTS.md` 与 `CODING_STANDARDS.md`（红线内：仅指针/引用行）

## 五栏

- 范围：读 `skills/verify-delivery/SKILL.md`（唯一真源）、`scripts/verify_hermetic.py`/`verify_secrets.sh`/`verify_docs_hygiene.sh`/`verify_citations.sh` 的头部口径、T18-EVIDENCE 的「收口指针清单」（5 处）、`recall-report.md` F06/F08/F16。
- 唯一写入路径：两文件中的指针/引用行。
- 验收口径（原始输出贴进 T26-EVIDENCE.md）：
  1. 两文件对 verify-delivery 技能与各门禁只留指针（技能/脚本为唯一真源），复制的规则正文清零或注明「判据见 X，勿复制」；
  2. `git diff --numstat` 对两文件的改动行全部是新增/修改的指针行（逐行说明）；
  3. `python3 scripts/verify_docs_hygiene.sh` 与 `bash scripts/verify_citations.sh AGENTS.md CODING_STANDARDS.md` 退出 0。
- 红线：AGENTS.md 有用户未提交的在飞改动——只动指针行，diff 中其他行零触碰；不改硬规则语义与三条闸门；不 commit/push/开 PR。
- 不接受的自由度：不许重排章节；不许顺手润色别的句子；指针必须指向存在的文件/节（过引证门禁）。

## 红绿纪律

先红后绿（红=复制正文的两份漂移形态在 selftest/引证口径下的对照说明）。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

AGENTS.md 6 条指针 + CODING_STANDARDS.md 2 条入口落地（全部新增行、硬规则与闸门零触碰）；技能/脚本成为判据唯一真源。

### 追记（出票方验收）

- 复跑：docs_hygiene 0 命中、引证 6/6 直配；变异演示：指针行号打歪 → 引证门禁越界判红，恢复逐字节一致。
- diff 抽查：新增行 = 6 指针 + 用户在飞自有行，删除行均属用户在飞改动。
- 残余裁决：T18 清单第 4/5 处（subagents.md §8.2 是五栏真源本身、skills/README.md 是生成物）**不做**，属有意简化，记入验收包；CODING_STANDARDS §1 工具表同理留白。
- 执行方纠正票面笔误（python3 跑 bash 脚本）属正确动作。
