# T18 测试 hermetic 门禁与交付验证技能（建议 11 环境半边 + 建议 12/14 的第 3 层）

Type: task
Status: resolved
Blocked by: T16
唯一写入路径: `scripts/`（红线内：新增 hermetic 检查脚本与 `verify.sh` 该层的接线行）+ `skills/`（红线内：create-verification-skill 产出的交付验证技能目录）

## 五栏

- 范围：读 `docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md` P12、`recall-report.md` F08/F09/F10/F14/F16、pstack 的 `/root/.dsh/skills/create-verification-skill/SKILL.md`（按其方法产出技能）、`docs/agents/subagents.md`（五段回报口径）。
- 唯一写入路径：`scripts/`（hermetic 检查脚本 + verify.sh 接线行）与 `skills/`（新技能目录）。
- 验收口径（原始输出贴进 T18-EVIDENCE.md）：
  1. hermetic 检查：tests 里读隐式环境（`os.environ`/代理/PATH/本机文件）的形态命中即红，自带已知坏样本红演示（--selftest）；
  2. 交付验证技能落地：技能文件存在且含「文案判据 / AI 味词表 / 中文 / 图·HTML 出口 / 改动说明格式」五节，每节可被引用（AGENTS.md/CODING_STANDARDS 只指针不复制——第 3 层最小化）；
  3. `bash scripts/verify.sh --layer scripts` 退出 0；
  4. 技能自证：给一个不合口径的样例文本，技能里的检查步骤能点出问题（演示输出贴证据）；
  5. P15-6：`skills/modules/llm_gateway/SKILL.md` 与实现同步（`config_status` 快照语义取代 async `is_configured`）。
- 红线：不改 AGENTS.md/CODING_STANDARDS.md 正文（指针更新属后续收口，先报清单）；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：不许把技能写成散文（每节要有可操作检查）；不许复制规则原文进技能（引用为真源，防两份漂移——红旗筛查结论）；不许扩大写入路径。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`verify_hermetic.py`（H1–H5，自检 10/10）+ `skills/verify-delivery/`（SKILL.md 五节 + check_copy.py 判据唯一真源）落地，verify.sh 接线 3 行，P15-6 的 SKILL.md 同步（3/3 行）。

### 追记（出票方验收）

- 复跑：hermetic 自检 10/10、全树 0 命中（豁免 2）、check_copy 自检 6/6。
- 变异演示：C2 判据词表四词全砍 → 自检红并精确点名「实得 C1,C3,C4,C5」——每条判据被钉住。变异经验：同义词表单删一词不算砍死，判据级变异要整条下刀。
- 层红归因认可（IE-10 → T22）；AGENTS.md/CODING_STANDARDS 的指针更新 → T26。
### 追记 2（Standards 轴 S1 的声明口径）

- skills/modules/llm_gateway/SKILL.md 的刷新授权在本票验收口径第 5 条（P15-6）；写入路径括号只写了「create-verification-skill 产出的技能目录」未同步、EVIDENCE 改动清单也没列它——声明与验收口径不一致属实，属声明文本欠账，记入验收包偏差表待用户追认，不做事后改写。
