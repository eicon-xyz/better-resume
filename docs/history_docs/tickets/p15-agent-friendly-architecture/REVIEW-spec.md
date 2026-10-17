# p15 Spec 轴评审报告（REVIEW-spec.md）

固定点 HEAD b09bbd2；评审面 = 各票「唯一写入路径」声明的改动（以各票 EVIDENCE 改动清单为权威，git diff 为辅）。方法：README 15 条建议 × 各票正文（范围/验收口径/红线/不接受的自由度）× 各票 EVIDENCE 三方比对，关键断言另在工作区机械复跑（票 Status、README 建议计数 15/0、八个新脚本与 skills/verify-delivery 存在性、resolver 的 build_for_model 与 getattr 清零、paraformer_rt close(1000)、eslint ignoreVoid:false、wait.py 存在）。

## 发现清单

### S1 · major · apps/api/src/better_resume/llm_gateway/resolver.py（T20-EVIDENCE.md「实现决定交代」末行）
类别：② 实现超出票面红线声明。
证据：T20 票面红线「不动其他 units 条目」；T20-EVIDENCE 自述「因本次代码移位，连带重锚了 LG-10（resolver.py:139-144、test_scene_resolver.py:175-184）与 LG-12（resolver.py:259-262）的 where 行号」。
为什么：票面把「不动其他 units 条目」列为红线，重锚 LG-10/LG-12 直接突破；理由（--strict 退出 0 必需）成立且已在票内交代，但出票方追记只裁了 LG-07/LG-09 并入 T22，未对这两条越权重锚给出裁决——属未经授权的偏差。

### S2 · minor · docs/tickets/p15-agent-friendly-architecture/T5-secrets-gate.md:4、T6-docs-hygiene-gate.md:4、T7-citation-gate.md:4
类别：④ 验收口径未兑现（票面状态）。
证据：三票 `Status: claimed`，但各自 EVIDENCE 完整、验收读数齐全，且被它们阻塞的 T8（Blocked by: T5,T6,T7,T10,T11）已 `resolved`。
为什么：建议 1 的核心主张是「Status 是唯一进度源、可查状态而非口头约定」，本阶段自己的三张票状态行与实际进度脱节，正是该建议要消灭的形态（frontier 口径下 claimed 合法，但与 T8 已 resolved 并存即自相矛盾）。

### S3 · minor · docs/tickets/p15-agent-friendly-architecture/T17-EVIDENCE.md:258、T22-EVIDENCE.md「实现决定交代」
类别：② 实现超出票面声明（已交代、待追认）。
证据：T17 票面红线「只改引证锚点（行号/范围/文件路径）」，实际刷新了 5 处 evidence 摘录（http-01/http-03/http-06/LG-06/LG-07 整块或整行）；T22 票面写入路径「锚点与必要时的 fix_record」，实际给 http-03 的 where 新增第 7 处引证（计数 340→341）。
为什么：刷新摘录与新增引证都不在「锚点/fix_record」字面内；理由（门禁绿但引证撒谎 = P09 形态）成立且票内逐条交代，但按硬规则 3，这类偏差应报用户确认后才算数，目前只有执行方自述 + 出票方追记。

### S4 · minor · docs/tickets/p15-agent-friendly-architecture/T10-citation-fence-exempt.md:12-15 与 docs/tickets/p15-agent-friendly-architecture/T10-EVIDENCE.md:90
类别：④ 验收口径未兑现 / ⑤ 偏差交代路径。
证据：T10 票面口径 2「p15 全目录扫描全部退出 0」实际 exit 1（4 条残留，证据原文承认「这一条没到 0，是本票的偏差」）；后续由出票方 Comments 改口径为「引证门禁扫描面排除 *-EVIDENCE.md」，并在 T8 接线里落地。
为什么：票面验收口径未达成，改口径的动作发生在 Comments 而非用户确认——偏差处理走了「出票方追认」而非硬规则 3 要求的「用户确认后才更新」。

### S5 · minor · apps/api/src/better_resume/llm_gateway/resolver.py:64-80（T12-EVIDENCE.md）
类别：③ 意图复述与实际改动偏离（措辞级）。
证据：README 建议 3「把『await 才有值』的判断改成同步值 API……判断用值不用协程」；实现是 `async def config_status(binding) -> ConfigStatus`，调用面仍 `status = await factory.config_status(binding)` 后才读 `status.configured`。T12 票面口径 2 的字面（「不存在『await 才有值』的布尔判断」）勉强兑现（布尔判断确实没了），但「判断用值不用协程」只兑现了一半——取值仍走协程，值对象化的是判定而非取回。
为什么：T12 的「实现决定交代」未把「config_status 仍是 async」列为自行拍定的决定，票面/建议与实现之间的这层措辞落差没有交代记录。

### S6 · minor · docs/tickets/p15-agent-friendly-architecture/README.md:47（建议 13）与 T25 票面
类别：① 建议要求了但实现没有（且阶段层无交代）。
证据：建议 13「HANDOFF 与会话断点是生成物（带 --check）」；T25 票面「不做 HANDOFF 生成物 --check（属会话工具链，见实现决定交代）」，T25-EVIDENCE 亦按票面不做；全阶段 26 张票无一承接这一半。
为什么：建议 13 的「远端状态可读化」半边落地（T25），「HANDOFF/会话断点生成物 + --check」半边被一张票有意划出后无人接手，README/收口层未见「砍单」交代（建议砍单本属「实施顺序与砍单待用户决定」节）。

### S7 · minor · T24-EVIDENCE.md:132-140（真票演示）
类别：④ 读数归属对不上。
证据：T24 真票演示 9 个越界文件里，docs/DECISIONS.md、docs/HANDOFF.md、docs/design/refs/** 四件可按 p14 在飞归属；docs/agents/domain.md、issue-tracker.md、subagents.md 三件在派单说明的 p14 在飞列举（docs/DECISIONS.md、docs/HANDOFF.md、docs/design/refs/**）之外，未见归属说明。
为什么：越界读数的归因清单没有覆盖全部 9 件，「p14 在飞」的解释对其中 3 件不成立或未证实。

### S8 · nit · docs/tickets/p15-agent-friendly-architecture/T24-write-scope-gate.md:15（验收口径 3）
类别：④ 验收口径读数与实况不符。
证据：票面预期「全层红若仅剩 IE-10 归 T22」；T24-EVIDENCE 实测当时层红是 4 条（IE-10 + http-09/so-04/identity_jobs-03 引 main.py 的锚点），证据自己也如实贴了 118/2/2。
为什么：票面对层红范围的预判与实测不符（后由 T22 收口），无实质后果，记录为口径写窄了。

### S9 · nit · docs/tickets/p15-agent-friendly-architecture/README.md:19（建议 1）与 T8-EVIDENCE
类别：⑤ 与提案的偏差未被交代。
证据：建议 1 说「verify.sh 增票据结构层」；实现是 ticket_frontier 两行并入既有 `--layer scripts`，没有独立「票据结构层」。
为什么：落点是更省的做法（复用层机制），但「建议说了单独一层、实现并进既有层」这层偏差没有在票面或证据里点名。

### S10 · nit · docs/tickets/p15-agent-friendly-architecture/README.md:33（建议 7）与 T15-EVIDENCE
类别：① 建议要求了但实现没有。
证据：建议 7「每个 verify/探针脚本自带『已知坏输入必红』自检」；compose_smoke.sh 与两个 drill 脚本无 --selftest，也未进 --layer scripts（需真跑栈）。T15 票面/证据未回应这一条是否适用。
为什么：要么建议 7 的「探针脚本」应读窄（仅 verify_* 门禁），要么部署面探针漏了自检口径——两种读法都该有一句交代，现在两份文档各说各的。

### S11 · nit · T22/T23/T25-EVIDENCE「实现决定交代」表
类别：④ 验收口径形状未兑现。
证据：各票模板统一要求「三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的」；T22 用「决定/依据/代价·边界」、T23 用「决策点/选择/理由与代价」、T25 用「决定/为什么这么定/放弃的替代·代价」。
为什么：语义近似覆盖（代价列通常含「没做的」），但「我明确没做的」这一栏在 T22/T23 里多次与代价混写，个别票（T25 §8 自检 skip 条目）没做项散落在正文而非表格——模板口径被软化。

## 明确未发现的面

- 未发现凭据、打码文本违规进入任何票据/证据/报告（T5 门禁自身在扫）。
- 未发现执行方伪造读数：抽到的读数（README 建议计数 15/0、resolver getattr 清零、build_for_model 进协议、close(1000)、eslint 配置、wait.py、八个新脚本）与工作区实况一致。
- 未发现 p14 在飞改动被 p15 票据认领或修改（T4/T11/T26 均有逐文件归属核对记录）。
- 各票「意图复述 + 实现决定交代」两段自述齐全（T24 的节名与三栏形状见 S11）。

## 未覆盖的面

- 未复跑任何 pytest / verify.sh 层 / compose 栈——读数核对以各票 EVIDENCE 原文与静态抽查为准，未独立复现数字。
- pitfalls-report.md / recall-report.md 的 [F..]/[P..] 32 条数据本身未逐条回溯到会话转录（超出本轴时间预算，仅核了其被引证的结构）。
- docs/audit/units/*.json 的 341 条引证语义未复核（T22 自身只抽 38 条；P15-7 已立案）。
- docs/agents/ 三份文件的改动归属（S7）未深挖——需要与 p14 派单记录比对才能定性。
- verify.sh / 各门禁脚本的代码级正确性（Standards 轴范围）。

## 自述与 diff 的核对方式

1. 先读 README 15 条建议与全部 26 张票正文 + PROBLEMS，建立「票面要求清单」。
2. 逐票读 EVIDENCE 的改动清单与验收读数，与票面口径逐条对表（兑现/偏差/交代三态）。
3. 对关键断言在工作区机械复跑（见开头方法段列出的 7 项抽查），全部与证据一致。
4. 红线核对以各票「红线/不接受的自由度」原文为判据，越界必须有出票方裁决或用户确认记录才算已交代。

## 需要人工裁定的条目

- S1（T20 越红线重锚 LG-10/LG-12）：技术上正确、事后看不可避免，但需出票方/用户对「红线突破 + 事后追认」这一处理方式表态。
- S3（T17/T22 刷新 evidence 摘录、新增引证）：同属「为诚实而超出票面字面」，按硬规则 3 应获用户确认后追认。
- S4（T10 口径 2 改为排除 EVIDENCE 文件）：改口径本身合理，但确认权在用户。
- S7（docs/agents/ 三件改动的归属）：需与 p14 派单记录核对后定性是 p14 在飞还是无主越界。
- S6（建议 13 的 HANDOFF/断点生成物半边）：砍单需用户点头，目前是事实性落空。
