# P14-T2 — 视觉 token 扩充（靛蓝色阶 / 渐变 / 阴影层级）

- Status: ready-for-agent
- Blocked by: T1
- 唯一写入路径：`apps/web/src/styles/tokens.css` 与消费它们的各 `*.module.css`（仅 token 替换，不改 JSX）

> 依据 README §1.5 视觉语言要点、D24。纪律：先红后绿（用守卫①②与既有测试兜底）。
## 目标
把 35 个 token 扩成一套可支撑「产品工具风 + Linear 细节」的体系：靛蓝 accent 色阶（主色/hover/active/弱化）、
渐变 token（hero、综合分、类别徽章三处点缀用）、阴影层级（卡片/浮层/吸底）、圆角与字阶微调、
间距补档；深色块（`prefers-color-scheme`）同步对齐同一套语义名。
## 红-绿切片
| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 新 token 全部有深浅双定义 | 守卫①对深色块报缺定义 → 修后绿 |
| 2 | 消费点迁移完整 | 旧色值引用清零（grep 旧 `--br-color-accent` 等旧名不复存在或有别名兼容说明） |
| 3 | 视觉不回退 | 172 例 + tsc/eslint 绿（样式层无行为） |
## 红线
- 不改任何 TSX/TS；不引 webfont；渐变只做点缀 token，不铺大面。
- 旧 token 名的删除要一次清干净消费点，不留死变量（守卫① 会抓）。
## 验收：`bash scripts/verify.sh --layer all` 绿；`grep -rn 'allow:' apps/web/src | wc -l` 与白名单一致；截图对照由页面批统一拍。
## 不做：组件样式（T3）、页面版式（T4–T8）。