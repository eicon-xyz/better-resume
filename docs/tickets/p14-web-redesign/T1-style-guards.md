# P14-T1 — 守卫闸门①②④ + 存量违规清零

- Status: ready-for-agent
- Blocked by: 无
- 唯一写入路径：守卫脚本（建议 `scripts/check_web_style_guards.py` 或 `apps/web/scripts/`，名可自定）+ `scripts/verify.sh`（web 契约层接线）+ 守卫脚本自身的测试 + 清存量涉及的 CSS 文件（见下）

> 依据 README §4.1 守卫清单、D22/D25。纪律：先红后绿；守卫自身必须先对**构造的坏输入**红一次，不许写成恒绿检查。
## 目标
把三条可机器判定的守卫做成会红的闸门并接进 verify 的 web 契约层：
① **token 零假变量**：CSS 里引用的每个 `--br-*` 必须有定义，--br-color-* / --br-gradient-* / --br-shadow-* 在 :root 定义的必须在深色块重述；② **全 CSS 树零裸 hex/px**（styles/tokens.css 除外；白名单注释制：`/* allow: <理由> */` 前一行放行）；④ **所有动画与过渡有 `prefers-reduced-motion` 处理**。
同时把存量违规清到零（守卫进 CI 即绿）：4 个假变量（`--br-text-muted` / `--br-border` / `--br-color-warning` / `--br-color-warning-bg`，见 `InterviewRoomPage.module.css:63`、`ResumePreviewCard.module.css:72-73`、`AiSettingsPage.module.css`）要么补定义要么换真 token；`MessageBubble.module.css:56` 的 blink 补 reduced-motion；`AiSettingsPage.module.css` 的裸 px/hex 改走 token（最小改动，版式重修属 T8）。
## 红-绿切片
| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 守卫对构造的坏输入会红 | 假变量/裸 hex/缺 reduced-motion 三类样例各报错且退出码非 0 |
| 2 | 守卫对当前仓库全绿 | 修存量后 exit 0 |
| 3 | 白名单注释生效 | 带 `/* allow: … */` 的裸值不报，无注释的报 |
| 4 | 变异证明 | 任一存量违规重新引入（如删 blink 的 reduced-motion 块）→ 守卫红 |
## 红线
- 守卫判定必须可机器复现（正则/解析），不许「看起来像」；判不了真的条款不许收（hover 覆盖率不进）。
- 不动 JS/TSX 业务逻辑；不动 `src/api`/`src/audio`/`src/stream`。
- 不新增依赖。
## 验收
| 命令 | 期望 |
| --- | --- |
| 守卫脚本对坏输入三类样例 | 各 exit 非 0，输出点名文件与条款号 |
| `bash scripts/verify.sh --layer all` | 全绿（含新守卫） |
| `pnpm -C apps/web test --run`、tsc、eslint | 全绿 |
## 不做
- 守卫③⑤（断点存在性、原生控件禁用）属 T3（组件与断点落地时再进闸门，避免长期红）。
- 不做守卫的可视化报告页。