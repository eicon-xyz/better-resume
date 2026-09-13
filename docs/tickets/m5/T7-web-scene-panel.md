# M5-T7 — 前端场景面板（查看 + 切换）

- blocking：M5-T2
- 纪律：先写失败测试（红），再实现（绿）

## 目标

让"换供应商"在界面上可完成、可解释：一个页面列出五个场景的当前绑定、目标、是否已配置，
并能切换（openai_compat ↔ xingyun）。不做用户/会话级粒度（Q3）。

## 交付物

- `src/api/client.ts`：`listScenes()` / `updateScene(scene, body)`（+ 契约类型再生）
- `src/scenes/queries.ts`：TanStack Query 封装（列表 + 变更 + 失效）
- `src/pages/AiSettingsPage.tsx` + 路由 `/settings/ai`：
  - 表格：场景（中文标签 + 技术名）/ 供应商 / 目标（model_ref 或 flow_id）/ 是否已配置
  - 每行一个切换控件（选择供应商 + 输入目标）+ 保存；保存失败显示可操作错误（复用 M3 的文案口径）
  - 未配置（缺密钥/缺 flow_id）→ 显式"未配置"徽标 + 提示缺哪个环境变量
  - 顶部一行说明："切换供应商不需要改业务代码，下一次 AI 调用即生效"
- 导航入口：chat 页头部加"AI 设置"链接
- 测试：`src/pages/AiSettingsPage.test.tsx`（≥6 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 列表渲染 | 五个场景都显示；中文标签与技术名同时可读 |
| 未配置标记 | configured=false 的场景显示"未配置"与缺失变量名 |
| 切换 | 选择 xingyun + 输入 flow_id → PUT 收到正确 body；成功后列表刷新 |
| 失败提示 | 422 时显示错误并按 M3 的口径给出可操作文案（不出现"未知错误"） |
| 权限 | 未登录 → 401 → 页面提示先登录（复用 LoginGate 或提示条） |
| 契约 | `pnpm check:api` 通过（类型与后端一致） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 全绿（152 → 更多） |
| `pnpm -C apps/web lint` / `typecheck` | 0 warning / 0 error |
| 人工 | 切换 extraction 场景到 xingyun 后，出题端点确实走星云（配合 T8 脚本观察日志） |

## 不做

- 不做绑定的新建/删除（五个场景固定，符合 D09 的范围裁剪）；
- 不做密钥输入框（密钥只从环境变量读，界面只显示"是否配置"）。

