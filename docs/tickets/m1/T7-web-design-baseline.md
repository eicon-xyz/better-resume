# M1-T7 — 前端设计基线（tokens + 基础组件）

- blocking：M0

## 目标

对齐 §12.2「design-system：先立 tokens」——把设计变量变成代码，避免 M2 面试界面再来一遍
（旧项目 DESIGN.md 与实现漂移的教训）。

## 交付物

- `apps/web/src/styles/tokens.css`：颜色/间距/圆角/字号/行高/层级/动效时长 CSS 变量
  （浅色 + 深色两套，`prefers-color-scheme` 跟随）
- `apps/web/src/components/`：`Button`、`Textarea`、`Card`、`Spinner`、`Collapsible`、
  `Empty`（每组件一个测试：渲染 + 交互/无障碍角色）
- 规则：组件只吃 tokens，不写魔法值；`pnpm -C apps/web lint` 必须绿

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 组件用例全绿 |
| `pnpm -C apps/web typecheck && pnpm -C apps/web lint` | exit 0 |
| 深色模式 | 切换系统主题后 token 生效（构建产物可验证） |

## 形态提议（待确认）

- **不引 shadcn/ui**（D05 提到）：M1 只需 6 个原子组件，自研 + tokens 更小更可控；
  如果面试界面（M2）需要表格/对话框等重组件再按需引入（Q2）。
- 不引 Tailwind（D05 未点名）；用 CSS Modules + tokens，避免样式方案反复。

## 不做

- 不做图标库、不做主题切换 UI、不做 Storybook。
