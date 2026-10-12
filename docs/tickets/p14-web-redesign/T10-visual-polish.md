# P14-T10 — 视觉批：交互反馈与质感补课

- Status: ready-for-agent
- Blocked by: 无
- 唯一写入路径：`apps/web/src/styles/tokens.css`（仅新增 `--br-text-hero` 一行）、`apps/web/src/components/**/*.module.css`、`apps/web/src/pages/**/*.module.css`、本票与 `T10-EVIDENCE.md`

> 依据 README §1.5 视觉语言要点、§4.1 测试缝（纯样式不写测试）、D24 / D25。纪律：不改 JSX/TS、不新增依赖、不 commit；只加状态与层级质感，不做版式重排。

## 目标

1. **字阶 hero 档**：`tokens.css` 新增 `--br-text-hero: 42px`（字号属非主题族，不需要深色重复定义），消费点为报告页综合分大数字；该处原以 `/* allow: … */` 放行的 42px 改走 token，随后删掉该 allow 行，`apps/web/src` 白名单由 48 条降到 47 条。既有 `--br-text-xs..xl` 的取值不动，不新增其他档。
2. **交互态补课**：给 Button（primary / secondary / ghost 三态）、Input / Select（hover 边框与 focus 环强化）、AppShell 导航项、SessionSidebar 会话项与删除键、页面可点行（上传页「继续上次面试」行、Table 行）补 hover / active / focus-visible 质感。只用既有 token（accent 系 / surface 系 / text-muted / border 系 / duration 系），不新增色值、不写裸 hex/px；过渡只用 `var(--br-duration-fast)`（120ms）或 `var(--br-duration-normal)`（200ms），且每条 `transition` 都在同文件 `@media (prefers-reduced-motion: reduce)` 内被同选择器重访。focus-visible 的全局环沿用 `styles/base.css`，不削弱、不移除。
3. **预留 token 落消费点**：T2 登记的四个预留 token 各落到真实消费点——`--br-color-accent-hover` / `--br-color-accent-active` 由 Button primary 的 hover / active 消费；`--br-color-accent-muted` 由导航与会话的选中态、可点行 hover 的弱背景消费（不做文字色）；`--br-radius-xs` 由 Badge 与同类小徽记（报告页与面试间的类别徽记）消费，不扩到卡片 / 按钮。

## 不做

- 不改 TSX / TS；不动业务逻辑、数据流、路由表；不碰 `apps/web/src/api`、`src/audio`、`src/stream`、`pages/chat/Composer.tsx`。
- 不新增依赖、不引 webfont 或动效库；不 commit。
- 不做页面版式重排（T4–T8 的范围）：只加状态与层级质感，不改布局结构与既有尺寸体系（除 hero 字阶一档）。
- 不改既有测试与断言；不改守卫脚本与守卫测试；不改 README、T1–T3 票、T4–T9 票与 T1–T3-EVIDENCE。
- 不新增渐变铺面：渐变仍只做 hero / 综合分 / 类别徽章三处点缀。
- 纯样式不新增单测（README §4.1 既定缝）；截图与浏览器手测不属本轮。

## 验收

| 命令 | 期望 |
| --- | --- |
| `python3 scripts/check_web_style_guards.py` | exit 0，末行 `check_web_style_guards: ok` |
| `grep -rn 'allow:' apps/web/src \| wc -l` | 47，逐条集合与 `T10-EVIDENCE.md` 白名单表一致 |
| 预留 token 消费 grep | `--br-color-accent-hover` / `--br-color-accent-active` / `--br-color-accent-muted` / `--br-radius-xs` 在 `tokens.css` 之外各 ≥1 处消费 |
| `pnpm -C apps/web test --run` | ≥186 passed（只增不减） |
| `pnpm -C apps/web typecheck`、`pnpm -C apps/web lint` | exit 0 |
| `bash scripts/verify.sh --layer all` | 末行 `ALL PASS (17 commands)`，exit 0 |
| 变异证明 `bash scripts/verify_mutation.sh` | 删 `--br-text-hero` 定义行 → 守卫红 → 恢复绿；恢复后 sha256 与逐字节一致 |

README §4.1 的「每个交互元素有 hover/active」不进守卫（判不了真伪），本票以 `T10-EVIDENCE.md` 的交互态清单 + 人工手测为口径；守卫 G4 只做 `transition` 必须有 reduced-motion 覆盖的机器兜底。
