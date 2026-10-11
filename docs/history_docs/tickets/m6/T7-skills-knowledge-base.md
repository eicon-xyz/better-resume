# M6-T7 — skills 知识库（repo-map + 模块 SKILL.md + API 索引）

- blocking：M5
- 纪律：**索引由脚本生成**并在 CI 检查漂移；SKILL.md 写"不变量 + 陷阱"，不复制代码

## 目标

D13：把仓库变成"自描述层"——人和 AI 都能先读 skills 再动手。学旧项目的 9 个 Skill，
但只做对我们有用的三类：**repo-map（去哪看）**、**模块 SKILL.md（不许违反什么）**、
**自动 API 索引（现在有什么）**。

## 交付物

- `skills/repo-map/SKILL.md`：模块路由表（"要改 X → 先看 Y"），覆盖 settings/identity/conversation/
  llm_gateway/ai_resilience/interview_engine/resume_parser/media/http/migrations/web；
  每条给"读哪几个文件 + 相关不变量 + 对应测试文件"
- `skills/modules/<module>/SKILL.md`（10 份左右）：每份 ≤ 80 行，固定结构：
  职责 / 对外接口 / **不变量（违反会出什么事）** / **已知陷阱（我们踩过的坑，引用 PROBLEMS 编号）** /
  测试地图 / 常见变更配方
- `scripts/extract_api_index.py`：从 `apps/api/openapi.json` + 前端路由生成
  `skills/api-index/generated-api-index.md`（端点表 + 权限 + 幂等语义 + 前端消费点）
- CI：`--check` 漂移检查（与 openapi.json / schema.d.ts 同级纪律）
- `skills/README.md`：怎么用（给人和给 agent 的两段说明）
- 测试：`tests/test_skills_index.py`（索引与 openapi 一致、每份 SKILL.md 含必需小节、行数上限）

## 测试

| 用例 | 断言 |
| --- | --- |
| 索引生成 | 脚本产出的端点集合 == openapi.json 的路径集合（含方法） |
| 漂移检查 | 手改生成文件后 `--check` 失败；重新生成后通过 |
| SKILL.md 结构 | 每个模块目录都有 SKILL.md；含"不变量/陷阱/测试地图"小节；≤80 行 |
| repo-map 覆盖 | docs 下列出的每个后端模块在 repo-map 里都有一行 |
| 交叉引用 | 提到 PROBLEMS 编号的条目确实存在于对应文件 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python scripts/extract_api_index.py --check` | 通过 |
| `uv run pytest -q tests/test_skills_index.py` | 全绿 |
| 人工 | 随机挑 3 个"要改 X"的问题，按 repo-map 能在 2 跳内找到入口（把过程记进验收文档） |

## 不做

- 不做旧项目那样的 9 个 Skill 全谱（词典/playbook 等留待需要时加）；
- 不把文档复制进 SKILL.md（只写不变量与陷阱，指向代码与测试）。

