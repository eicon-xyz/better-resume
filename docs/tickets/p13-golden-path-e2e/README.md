# P13 提案：假模型驱动的黄金路径 E2E（把语义层手测搬进 verify）

> **依据**：P12 收口后的讨论（2026-10-11）。现状结论均带 `文件:行号`；决策待用户逐条拍板（§6）。
> **状态**：已规格化，**待用户点头**。

## 1. 范围

### 1.1 一句话

让「上传简历 → 出题 → 答题 → 追问 → 报告」这条产品主干在**真栈 + 假供应商**上可一键复跑、真断言、留证据，
并把 `docs/MANUAL-TESTING.md` §1.5 里**语义层**的手测项搬进 verify 分层。

### 1.2 现状（已核实，不是推断）

| 现状 | 依据 |
| --- | --- |
| 黄金路径脚本**已存在**且走完整链路（上传→答题→结束→打印报告），简历 PDF 用 reportlab 现场生成 | `apps/api/scripts/interview_smoke.py:1`（docstring 自称 "Real end-to-end interview smoke"） |
| 但它**要真 key**（`BR_DEEPSEEK_API_KEY`）、**只打印不判定**、**不在任何 verify 层** | 同上 docstring；`bash scripts/verify.sh --list` 的 real 层只有 real_model_smoke / media_smoke×2 / assembler_real_probe / v3_ws_probe |
| 假供应商已就位：`fake-llm` 服务在 `smoke` profile 下，`compose_smoke.sh` 已经用它起栈 | `compose.yaml:241-242`；`scripts/compose_smoke.sh:7`（"The SSE check uses the `smoke` profile's fake vendor"） |
| **假供应商的 questions 场景不产出 `category`** | `apps/api/scripts/fake_openai.py:56-67`（只有 `topic` / `focus_points` / `text`） |
| 因此 P11 之后所有走假供应商的检查，**测的都是 D23 的规则回退路径**，不是「模型给出合法类别」那条主路径 | `docs/DECISIONS.md` D23（非法或缺失回退到规则推断）；`ACCEPTANCE.md`（P11）「非法值在 schema 层降为 None，不炸整批」 |
| 而 `fake_openai.py` 自称有防漂移守卫：「`tests/test_fake_openai.py` validates every payload against the real pydantic contracts, so the fake **cannot silently drift**」 | `apps/api/scripts/fake_openai.py:25-26` |
| **守卫没拦住**：`category` 缺失时 payload 仍能通过 pydantic 校验（字段可空 → None → 回退），所以「验能解析」不等于「覆盖了契约新增的受控字段」 | 同上两处对照 |
| `compose_smoke.sh` 走的是**部署面**，面试业务路径一步没走 | `scripts/compose_smoke.sh:102-174`（config / SPA / 缓存头 / 非 root / REST / SSE / WS / --scale / 心跳 / 限流 scope） |
| 栈内查库的既有模式可复用 | `scripts/compose_smoke.sh:110`、`scripts/kill_instance_drill.sh:97`（`docker compose exec -T postgres psql -v ON_ERROR_STOP=1`） |
| 手测清单 §1.5 第 9–13 项目前全靠人在浏览器里点 | `docs/MANUAL-TESTING.md` §1.5 |

### 1.3 本阶段要做的五件事

1. **补假供应商的契约覆盖**：questions 场景产出带**合法 `category`** 的 `QuestionBatch`；并保留一种「不给 category」的形态用于测回退（两条路径都要能测）。
2. **收紧防漂移守卫**：`tests/test_fake_openai.py` 不只验「能被 pydantic 解析」，还要验「契约里的**受控枚举字段**在 fake 的 payload 里真的出现过合法值」。
3. **黄金路径可断言**：`interview_smoke.py` 支持假模型 + 断言模式（走 nginx，退出码判定），**一份实现两种调用**（real 层继续用真模型打印，e2e 层用假模型断言）——不做两份实现。
4. **降级路径进断言**：无文本层 PDF、技能与语料无关两种 fixture，断言「仍出 5 题 + 降级原因落库 + 响应/报告明示」。
5. **接进 verify 分层 + 重划手测清单**：新增 `e2e` 层（或并入 `deploy`，见 §6 Q1），同步 `--list` 层图与 `tests/test_verify_script.py`；`MANUAL-TESTING.md` §1.5 按「哪些已被自动化」重划。

### 1.4 手测能摘掉多少（**修正我在 P12 期间的说法**）

我先前说过「P13 做完，§1.5 那五条手测就能从你手上摘掉」——**这话说过头了**。逐项拆开：

| §1.5 项 | 语义层（可自动化） | 渲染/真模型层（**仍须手测**） |
| --- | --- | --- |
| 9 面试侧重下拉 | `interview_type` 落库为 `project`；非法值回退 `auto` | 下拉控件本身；**「题目整体偏项目」依赖真模型是否理会配比提示，假供应商测不出** |
| 10 无文本层 PDF | 不报错、仍出 5 题、`resume_warnings` 落库、降级原因可见 | 上传页预览卡片的视觉呈现 |
| 11 技能与语料无关 | 仍出题、降级原因为「未匹配到八股语料」 | 同上 |
| 12 按类给分一节 | `category_breakdown` 结构正确；某类 < 2 题 → 不出分数 + 「样本不足」 | 报告页那一节的**视觉呈现**；雷达图与新一节并存的样子 |
| 13 按类与逐题一致 | 每题 `category` 与聚合一致；追问继承主问题类别 | 逐题回放 UI 上的对照 |

净结果：**语义断言全部搬进 CI/nightly，手测项从「验语义 + 看渲染」缩到「只看渲染」**——手测会更快更浅，但不会归零。

## 2. 不做（本阶段明确排除）

- **不做浏览器自动化**（ego lite / Playwright 等）：新依赖要先单独提案（D04/D17 依赖纪律），且渲染层判断本来就该留给人。
- **不做「Agent 可探索环境」的其余三件**（只读查库/查日志通道、数据准备与重置 CLI、统一测试 CLI）：那是外部实践里更大的一块，本阶段只做黄金路径。若本阶段跑通，另开 P14。
- **不碰真机层**：`real` 层的预算守卫、四条真机链路一律不动。
- **不做 Agent Eval**（出题质量 / 评分一致性）：那是独立议题，另开提案。
- **不改 `compose.yaml` 的服务拓扑**（只可能加环境变量透传，且必须三处同步）。
- 不改 `AGENTS.md`；不动 `docs/tickets/p11-*`、`docs/tickets/p12-*`、`docs/history_docs/**`。

## 3. 交付物

| 交付物 | 落点 |
| --- | --- |
| 假供应商产出合法 `category`（并保留无 category 的形态） | `apps/api/scripts/fake_openai.py` |
| 收紧后的防漂移守卫 | `apps/api/tests/test_fake_openai.py` |
| 可断言的黄金路径（假模型 + 走 nginx + 退出码） | `apps/api/scripts/interview_smoke.py` |
| 降级路径 fixture 与断言 | 同上 + `apps/api/tests/`（若需要单元级） |
| 新层接线与层图 | `scripts/verify.sh` + `apps/api/tests/test_verify_script.py` |
| 手测清单重划 | `docs/MANUAL-TESTING.md` §1.5 与 §4 |
| 验收包 | `docs/tickets/p13-golden-path-e2e/ACCEPTANCE.md`（含 `var/evidence/` 读数抄录） |

## 4. 测试与验收口径

### 4.1 红-绿垂直切片

| # | 用例 | 断什么 |
| --- | --- | --- |
| T1 | fake 的 questions payload | 含合法 `category`（三枚举之一）；**先红**：现有 payload 无该字段 |
| T1 | 守卫能抓住受控字段缺失 | 把 `category` 从 payload 里删掉 → 守卫测试**变红**（这一条是「守卫本身要被验证」，D22） |
| T2 | 假模型跑通黄金路径 | 上传 → 5 题 → 答题 → 追问 → 结束 → 报告，全走 nginx，退出码 0 |
| T2 | 断言真的会红 | 故意改坏一处断言（如期望 4 题）→ 脚本**非 0 退出**；不是只打印 FAIL |
| T4 | 无文本层 PDF | 仍出 5 题；`resume_warnings` 落库；降级原因在响应/报告里明示 |
| T4 | 技能与语料无关 | 仍出题；降级原因为「未匹配到八股语料」 |
| T4 | 类别与配比 | `category` 落库为合法枚举；追问 `category` == 主问题 `category`；`category_breakdown` 与逐题一致；某类 < 2 题 → 「样本不足」 |
| T3 | 层图与守卫同步 | `verify.sh --list` 含新层；`test_verify_script.py` 钉住层图（P44/P9 的既有机制） |

### 4.2 阶段验收（用户视角）

一条命令跑完黄金路径并给出 PASS/FAIL 与证据目录；`MANUAL-TESTING.md` §1.5 里被自动化的项**明确标注**已由哪一层覆盖，剩下的只有渲染与真模型行为。

### 4.3 复跑命令与回归底线

```bash
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR='/root/better resume/.cache/uv'
cd apps/api && export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
rm -f /tmp/x.xml && uv run pytest -q --junitxml=/tmp/x.xml      # 例数看 xml 读数
cd '/root/better resume' && bash scripts/verify.sh --layer all
bash scripts/compose_smoke.sh                                   # 部署面不得变红
```

回归底线：后端全量 pytest **0 skipped**（不导出 `BR_*` 会静默吞掉 136 例）；`--layer all` 全绿；
`compose_smoke.sh` 与 `kill_instance_drill.sh` 不得变红；`verify_audit_evidence.py --structural` 读数不变。

**沙箱限制（已知）**：`docker compose build` 在 `workspace-write` 沙箱下会因 buildx 要写工作区外而失败——
起栈的步骤需要提权或由用户在宿主机跑（`docs/HANDOFF.md` §4）。这一条会限制 AI 能自证到哪一步，验收包必须写清哪些读数是用户跑的。

## 5. 预估

| 工作包 | 规模 | 说明 |
| --- | --- | --- |
| T1 假供应商 + 守卫 | S–M | payload 加字段容易；**守卫要能红**才是重点 |
| T2 黄金路径可断言 | M | 现有脚本要加 `--model` 与断言模式，且不能变成两份实现 |
| T3 接线与层图 | S | 但要同步 `--list` 层图与 `test_verify_script.py`（P44/P9 钉过） |
| T4 降级与类别断言 | M | 两份 fixture（无文本层 PDF、无关技能简历）+ 查库断言 |
| T5 手测清单重划 | S | 纯文档，但要逐项标清「已被哪一层覆盖」 |

**最大风险**：① 起栈在沙箱里跑不了（`docs/HANDOFF.md` §4），AI 可能只能交付脚本而无法自证端到端读数——**这一条必须在提案阶段就说清，不能到验收才暴露**；
② 假供应商改 payload 会牵动 `test_fake_openai.py` 与所有走 `smoke` profile 的既有检查（`compose_smoke.sh` 的 SSE 断言）；
③ 一份实现两种调用容易长成「默认关闭没人跑」的分支（`AGENTS.md` §开发规范 清洁度）——两种调用都必须真的被某一层跑到。

## 6. 需要用户决定的问题

**无。** Q1–Q4 已由用户拍板（2026-10-11）：

| # | 问题 | 决定 |
| --- | --- | --- |
| Q1 | 新层还是并入 `deploy` | **新层 `e2e`**——部署面失败与业务路径失败是两类故障，混在一层里红灯难读。`verify.sh` 的层计划、`--list` 层图、`test_verify_script.py` 必须同步（P44/P9 钉过层图逐字） |
| Q2 | 假供应商要不要保留「不给 `category`」的形态 | **要**（按 prompt 里的标记切换）——D23 的回退是真实生产分支，只测「给了 category」等于回退逻辑无人看守。**两个模式都必须被某一层真的跑到**，否则违反清洁度规则（不许留「默认关闭没人跑」的分支） |
| Q3 | 起栈跑不了时怎么验收 | **(a)**：AI 交脚本 + 单元级断言，端到端读数由**用户在宿主机跑并回填**。验收包必须明确区分「AI 自证的读数」与「用户跑的读数」，不许混在一张表里 |
| Q4 | 阶段目录名 | `p13-golden-path-e2e` |
