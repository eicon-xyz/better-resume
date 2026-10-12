# P14-T3 — 页壳 + 断点 + 样式化组件 + 守卫③⑤

- Status: ready-for-agent
- Blocked by: T2
- 唯一写入路径：`apps/web/src/components/`（AppShell 族与新组件）、`apps/web/src/App.tsx`（接线）、各页面 JSX 中**控件替换的最小改动**、守卫脚本（追加③⑤）与 verify.sh

> 依据 README §1.4 页壳线框、§4.1 守卫③⑤。纪律：先红后绿；行为单测只写带逻辑的（导航高亮）。
## 目标
1. **页壳**：顶栏（产品名 + 主导航「对话 / 面试 / AI 设置」+ 右上用户区与退出）+ 居中内容容器（max-width ≈ 1200）；聊天页会话侧栏降为页内二级栏；页内 header 收敛为标题行。
2. **两档响应式**：≥1024 双栏照旧；<1024 两列塌单列、二级栏顶部折叠；全站至少一条宽度断点（守卫③）。
3. **样式化组件**：Select / Input / Table / Badge / Skeleton，替换既有裸控件（守卫⑤：页面不裸用 `select/input/table`）。
## 红-绿切片
| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 导航高亮行为单测 | 当前路由对应导航项带选中态（公开可见 class/aria） |
| 2 | 守卫③先红后绿 | 断点未加 → 红；加 ≥1 条宽度断点 → 绿 |
| 3 | 守卫⑤先红后绿 | 构造裸 `<select>` 样例 → 红；替换后全仓绿 |
| 4 | Skeleton 开关行为 | 加载态出现/消失（如组件带该逻辑） |
## 红线
- 不改业务逻辑与数据流（TanStack Query/zustand 用法不动）；不动路由表（新导航项只指向既有路由）。
- 原生控件替换只做**等价替换**（值/事件/受控语义不变），版式重修属页面票。
- 不新增依赖。
## 验收
| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 172 例不红 + 新增行为单测绿 |
| `bash scripts/verify.sh --layer all` | 绿（守卫①–⑤全开） |
| `pnpm -C apps/web typecheck && pnpm -C apps/web lint` | 绿 |
## 不做：页面内部版式（T4–T8）；登录门 hero 化（T4 之前它仍能用）。