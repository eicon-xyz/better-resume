# CODING_STANDARDS.md

`/code-review` 的 **Standards 轴**读这份文件；**实现期的必读清单是 `AGENTS.md`**（它会被推进每个 agent 的上下文）。
本文件只放**判断类标准与指针**，不复制 `AGENTS.md` 的规则原文——两份原文必然漂移。

## 1. 先跳过工具已经拦下的

单一入口 `scripts/verify.sh`（CI 与本地同一份命令，P2-T1）。评审时**不要重复报**这些：

| 层 | 命令 | 覆盖 |
| --- | --- | --- |
| 格式/静态 | `ruff format --check`、`ruff check`、`eslint`、`tsc` | 格式、未用变量、类型错误 |
| 迁移 | `alembic check` | 模型与迁移漂移 |
| 契约 | 契约三件套（`export_openapi.py` → `gen:api` → `extract_api_index.py --check`） | 前后端契约漂移（M6 P16） |
| 测试 | `pytest` + `vitest` + `scripts/` 回归 | 行为回归 |
| 覆盖率 | `scripts/check_coverage_floors.py` | 深模块 per-module 底线 |

## 2. 仓库标准（读这几节，不要凭印象）

- **`AGENTS.md` §开发规范**：实现期硬约束（mock 边界、`ai_resilience` 链、503 语义、缓存 TTL、WS 关闭码、连接参数、证据诚实、依赖纪律、清洁度）。
- **`AGENTS.md` §贡献指南（提交前检查清单）**：改动类型 → 必跑命令。
- **`AGENTS.md` §AI 智能体须知**：P15–P34 踩坑清单，用来对照「这个改动会不会重蹈覆辙」。

评审口径（不是复读规则）：

- 规则被**违反**且能引用原文 → 硬违规。
- 规则**没覆盖**、但改动与周围风格/既有模式不一致 → 判断项，写「可能……」。
- 测试写在了**未经用户确认的缝**上 → 缺陷（P1-A 复盘）。
- 新依赖没在提案里说明 → 缺陷（D04/D17）。

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
