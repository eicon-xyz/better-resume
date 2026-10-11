# CODING_STANDARDS.md

`/code-review` 的 **Standards 轴**读这份文件；**实现期的必读清单是 `AGENTS.md`**（它会被推进每个 agent 的上下文）。
本文件只放**判断类标准与指针**，不复制 `AGENTS.md` 的规则原文——两份原文必然漂移。

## 1. 先跳过工具已经拦下的

单一入口 `scripts/verify.sh`（CI 与本地同一份命令）。评审时**不要重复报**这些：

| 层 | 命令 | 覆盖 |
| --- | --- | --- |
| 格式/静态 | `ruff format --check`、`ruff check`、`eslint`、`tsc` | 格式、未用变量、类型错误 |
| 迁移 | `alembic check` | 模型与迁移漂移 |
| 契约 | 契约三件套（`export_openapi.py` → `gen:api` → `extract_api_index.py --check`） | 前后端契约漂移 |
| 测试 | `pytest` + `vitest` + `scripts/` 回归 | 行为回归 |
| 覆盖率 | `scripts/check_coverage_floors.py` | 深模块 per-module 底线 |

## 2. 仓库标准（读这几节，不要凭印象）

- **`AGENTS.md` §开发规范**：实现期硬约束（mock 边界、`ai_resilience` 链、503 语义、缓存 TTL、WS 关闭码、连接参数、证据诚实、依赖纪律、清洁度）。
- **`AGENTS.md` §贡献指南（提交前检查清单）**：改动类型 → 必跑命令。
- **`AGENTS.md` §AI 智能体须知**：改某个模块前先对照它的约束，判断「这个改动会不会重蹈覆辙」。

评审口径（不是复读规则）：

- 规则被**违反**且能引用原文 → 硬违规。
- 规则**没覆盖**、但改动与周围风格/既有模式不一致 → 判断项，写「可能……」。
- 测试写在了**未经用户确认的缝**上 → 缺陷。
- 新依赖没在提案里说明 → 缺陷（D04/D17）。
- 声称「我验证了 X」的脚本/输出必须真的检查退出码或断言 → 只打印结论、不判定的验证脚本视为缺陷（例：先印「RED (expected)」再跑，红没红都退 0）。

## 3. 无明文规定时的兜底：Fowler 坏味道基线

`/code-review` 自带一份坏味道基线（Mysterious Name / Duplicated Code / Feature Envy / Data Clumps /
Primitive Obsession / Repeated Switches / Shotgun Surgery / Divergent Change / Speculative Generality /
Message Chains / Middle Man / Refused Bequest）。两条约束：**仓库明文标准永远优先**；
**坏味道永远是判断项**（写成「可能的 Feature Envy」），不是硬违规。

## 4. 新规则该放哪（先分类，再决定落点）

| 规则形状 | 落点 |
| --- | --- |
| 固定语法 / 被禁 API / import 形状 / 文件位置 | **自动检查**（ruff 规则、eslint 规则、CI job、pre-commit）——默认选这个 |
| 跨文件一致性、「跟周围风格保持一致」 | 本文件 |
| 实现期必须遵守的硬约束 | `AGENTS.md` §开发规范 |
| 导航指针（「改 X 先看哪」） | `AGENTS.md` / `skills/repo-map/` |

`/retro` 提出新规则时按这张表分类；**能变成检查的，就不要写成人读的规则**。

## 5. 人工评审的高风险面

工具拦不下的五类面，评审时逐类做一次检查动作；每格是「看什么」，不是一条规定（规定在 `AGENTS.md`）。

| 类 | 看什么 | 出处 |
| --- | --- | --- |
| 权限与认证 | 这次改动有没有新增或移动端点的鉴权依赖、session 校验、WS ticket 校验的位置？ | `docs/DECISIONS.md` D11、`identity/` |
| 状态变化与幂等 | 幂等键（`request_id`）的生效范围有没有变？报告冻结、题级锁的边界有没有被绕过？ | `GLOSSARY.md`（幂等键 / 报告冻结）、`interview_engine/` |
| 并发与重试 | 供应商调用有没有绕过 `ai_resilience` 链？`--scale api=2` 下这次改的状态是进程内还是跨副本共享？ | `docs/DECISIONS.md` D19/D20、`AGENTS.md` §开发规范 |
| 数据一致性与迁移回滚 | 有没有新迁移？它能不能 downgrade？模型与迁移有没有漂移？JSONB 字段的语义有没有被复用成两种含义？ | `bash scripts/verify.sh --list` 的 contract 层（`alembic check`） |
| 对外契约与降级语义 | `openapi.json` / `schema.d.ts` 变没变（契约三件套跑没跑）？依赖不可用时是不是 503 + Retry-After？降级有没有**明示**？WS 关闭码对不对？ | `AGENTS.md` §开发规范（错误语义 / WS 转写）、`docs/DECISIONS.md` D23 |

## 6. 评审必答问题

不能变成会红的测试、但在实现期必须遵守的判断类规则，在这里改写成评审期逐条必答的问题；条数上限 8。每条必须指回既有规则（文件 + 节名），不许发明新规则；证据只接受三种形式：命令 + 原始输出摘录、`文件:行号`、`文件:节名`（决议用 D 号，因为 `docs/DECISIONS.md` 是一张表，按 D 号引用是本仓库既有惯例，用行号反而不稳）；不接受「已确认」「检查过了」这类无证据回答；「不适用」是合法回答，连续多轮回答「不适用」的条目进入 T4/T5 的删除候选流程。

- **这次改动里，哪些结论的依据是「系统返回了什么」而不是「契约/决议要求什么」？**
  证据：每个这类结论依赖的命令 + 原始输出摘录，或契约/决议的 `文件:节名`；主张与契约不一致时贴出两边原文。
  不适用：本次改动没有引入以实测系统返回为准的结论。
  出处：`AGENTS.md` §开发规范（证据诚实）、`docs/audit/CONTRACT.md`。

- **有没有新增的抽象或机制，找不到一个会变红的检查来钉住它？**
  证据：新增抽象或机制的 `文件:行号`，以及钉住它的检查——`scripts/verify_mutation.sh` 的基线绿 → 变异红 → 恢复绿记录，或一个会变红的断言。
  不适用：本次改动没有新增抽象或机制。
  出处：`docs/DECISIONS.md` D22、`scripts/verify_mutation.sh`。

- **有没有测试写在了未经用户确认的缝上？**
  证据：新增测试的 `文件:行号`，以及用户确认该缝的位置（对话或票据）。
  不适用：本次改动没有新增测试。
  出处：`AGENTS.md` §开发规范（TDD 循环纪律）、`CODING_STANDARDS.md` §2。

- **有没有 mock 了内部模块，而不是系统边界（LLM/时钟/Redis/讯飞/浏览器音频/IPC）？**
  证据：每个新增或改动的 mock 的 `文件:行号` 和它替换掉的对象；落在系统边界之外的逐个点名。
  不适用：本次改动没有新增或改动 mock。
  出处：`AGENTS.md` §开发规范（只 mock 系统边界）。

- **有没有新增「默认关闭、没人跑」的分支或设置？新设置有没有三处同步（`settings/config.py` / `compose.yaml` / `.env.example`）？**
  证据：新设置的默认值，以及它在 `compose.yaml` 与 `.env.example` 里的对应行（`文件:行号`）；若默认关闭，指出哪一层会真的跑它。
  不适用：本次没有新增分支、也没有新增设置。
  出处：`AGENTS.md` §开发规范（清洁度 / 设置新增）。

- **有没有引入被决议排除的依赖，或没在提案里说明的新依赖？**
  证据：依赖清单的改动（`pyproject.toml` / `package.json` 的 `文件:行号`）与提案里说明它的位置；没有新增依赖就给出依赖清单未改动的状态。
  不适用：本次改动没有触碰依赖清单。
  出处：`docs/DECISIONS.md` D04/D17、`AGENTS.md` §开发规范（依赖纪律）。

- **跨进程可见的缓存或配置缓存，有没有 TTL 或写路径失效？**
  证据：缓存写入点的 `文件:行号`，以及 TTL 参数或失效调用；多副本下只在本地失效的，指出它的跨副本可见性。
  不适用：本次改动没有新增或改动跨进程可见的缓存。
  出处：`AGENTS.md` §开发规范（缓存）。

- **用例动过的跨进程共享状态（如场景绑定表），有没有由 fixture 快照还原？**
  证据：动过共享状态的用例的 `文件:行号`，以及快照/还原 fixture 的 `文件:行号`。
  不适用：本次改动的用例没有动跨进程共享状态。
  出处：`AGENTS.md` §开发规范（测试的共享状态自己还原）。

