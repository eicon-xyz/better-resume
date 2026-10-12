# P14-T10 验收包 — 视觉批：交互反馈与质感补课

- 票据：docs/tickets/p14-web-redesign/T10-visual-polish.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.5 / §4.1 / §4.3；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

本票只做三件「质感补课」，不动版式与业务：

1. **字阶 hero 档**：tokens.css 新增 `--br-text-hero: 42px`，消费点为报告页综合分大数字；该处原本以 allow 放行的 42px 改走 token，allow 白名单 48 → 47。既有 `--br-text-xs..xl` 取值不动，不加其他档。
2. **交互态补课**：给 Button / Input / Select / AppShell 导航项 / SessionSidebar 会话项与删除键 / 页面可点行（上传页「继续上次面试」行、Table 行）补 hover / active / focus-visible 质感；只用既有 token，过渡统一 `var(--br-duration-fast)`（120ms），每条 transition 在同文件 `@media (prefers-reduced-motion: reduce)` 内被同选择器重访。
3. **预留 token 落消费点**：`--br-color-accent-hover` / `--br-color-accent-active` 由 Button primary 的 hover / active 消费；`--br-color-accent-muted` 由导航与会话的选中态、可点行 hover 的弱背景消费；`--br-radius-xs` 由 Badge 与同类小徽记消费。

不做：不改 TSX/TS、不动业务逻辑/数据流/路由表、不碰 `src/api`/`src/audio`/`src/stream`、不新增依赖、不做页面版式重排、不改守卫脚本与既有测试、不 commit。

## 二、实现决定交代

### 2.1 hero 字阶

- tokens.css 在 `--br-text-xl: 26px;` 之后新增一行 `--br-text-hero: 42px;`。字号属非主题族，不在深色块重述——G1b 只对 `--br-color-` / `--br-gradient-` / `--br-shadow-` 前缀要求深浅双定义（守卫脚本 check_web_style_guards.py:35 的 `THEME_PREFIXES`）。
- 唯一消费点是 InterviewReportPage.module.css 的 `.overall`（报告页综合分大数字，JSX 的 `aria-label=综合得分` 元素）：42px → `var(--br-text-hero)`，并删除其上一行的 allow 注释。
- `--br-text-xs..xl` 的值一个未改，未新增其他字阶。

### 2.2 交互态

- **Button**：transition 声明集中在 `.button`（background / border-color / color，均 `var(--br-duration-fast)`）。primary hover → `--br-color-accent-hover`、active → `--br-color-accent-active`；secondary hover → `--br-color-surface`、active → surface + `--br-color-text-muted` 边框；ghost hover → surface + `--br-color-text`、active → `--br-color-border` 底作按下反馈。白名单允许的「border 系」用于交互底/边框色，未引入新色值。
- **Input / Select**：hover 边框 → `--br-color-accent`；focus-visible 在全局环之上加「边框 accent + 4px `--br-color-accent-muted` 光晕」（`var(--br-space-1)`），环宽不写裸 px。全局 `:focus-visible`（base.css:18-22）未改、未削弱。
- **AppShell 导航项**：hover → surface + `--br-color-text`；active → `--br-color-accent-muted`；选中 `.navActive` 沿用既有 accent-muted 弱背景。
- **SessionSidebar**：会话项 hover → `--br-color-surface-raised` + border；`:active` 与选中 `.active` 用 `--br-color-accent-muted` 弱背景 + `--br-color-accent` 边框；删除键 hover → `--br-color-danger`；折叠 summary hover → `--br-color-text`。
- **页面可点行**：上传页 `.sessions li`（「继续上次面试」列表行）hover → `--br-color-accent-muted` 弱背景；Table 组件 `.table tbody tr` hover → `--br-color-surface-raised`。两者都不加内边距/外边距，不改行高，只加底色与圆角，无版式位移。
- 所有新增 transition 都是 `var(--br-duration-fast)`（120ms，≤200ms 上限）；reduced-motion 覆盖见 §3.3，G4（守卫④）机器兜底见 §3.1。

### 2.3 radius-xs 与 accent-muted 的落点

- `--br-radius-xs` 只落在徽记类：Badge 组件 `.badge`（pill → xs），以及同类小徽记 RoomParts.module.css `.badge`、InterviewReportPage.module.css `.badge`；未扩到卡片、按钮、输入控件。
- `--br-color-accent-muted` 只作弱背景（导航 active / 会话选中 / 行 hover / focus 光晕），未作文字色。

### 2.4 守卫与白名单口径

- 未新增 allow；删除 1 条（InterviewReportPage.module.css 的综合分 42px 行），白名单实测 47。
- 未改 `scripts/check_web_style_guards.py`、`apps/api/tests/test_web_style_guards.py`、`scripts/verify.sh`、`styles/base.css`；未改任何 TSX/TS。
- 新增的混合简写（`box-shadow` 光晕）不含裸 px/hex；G2 通过。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行，前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
~~~

### 3.1 守卫与白名单

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0

$ grep -rn 'allow:' apps/web/src | wc -l
47
~~~

数字：退出码 0；扫描 27 个 .css；违规 0；末行 ok；白名单 47 条（较原 48 少 1）。

47 条逐条（文件:行号 — 理由）：

~~~text
apps/web/src/styles/base.css:19:  /* allow: 键盘焦点外框线宽（2px 几何） */
apps/web/src/styles/base.css:21:  /* allow: 焦点外框与控件的偏移（2px 几何） */
apps/web/src/components/Table.module.css:12:  /* allow: 表格行底分隔线线宽（1px 几何） */
apps/web/src/components/AppShell.module.css:12:  /* allow: 顶栏底部分隔线线宽（1px 几何） */
apps/web/src/components/Button.module.css:6:  /* allow: 按钮发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Collapsible.module.css:2:  /* allow: 折叠面板发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Collapsible.module.css:31:  /* allow: 折叠箭头三角形的边长（8px 几何） */
apps/web/src/components/Collapsible.module.css:33:  /* allow: 折叠箭头三角形的边长（8px 几何） */
apps/web/src/components/Collapsible.module.css:35:  /* allow: 折叠箭头两条边的线宽（1.5px 几何） */
apps/web/src/components/Collapsible.module.css:37:  /* allow: 折叠箭头两条边的线宽（1.5px 几何） */
apps/web/src/components/Spinner.module.css:7:  /* allow: 加载点直径（12px 环径几何） */
apps/web/src/components/Spinner.module.css:9:  /* allow: 加载点直径（12px 环径几何） */
apps/web/src/components/Spinner.module.css:11:  /* allow: 加载环线宽（2px 几何） */
apps/web/src/components/Card.module.css:3:  /* allow: 卡片发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Textarea.module.css:5:  /* allow: 输入区发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Input.module.css:4:  /* allow: 控件发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Empty.module.css:7:  /* allow: 空态占位框发丝虚线线宽（1px 几何） */
apps/web/src/components/Select.module.css:3:  /* allow: 控件发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:38:  /* allow: 题号列最小宽度（24px 列表几何） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:73:  /* allow: 降级提示左侧警示条宽度（3px 几何） */
apps/web/src/pages/interview/RadarChart.module.css:7:  /* allow: 雷达图画布最大宽度（260px 画布尺寸） */
apps/web/src/pages/interview/RadarChart.module.css:35:  /* allow: 雷达图轴标签字号（9px，随画布缩放） */
apps/web/src/pages/interview/RoomParts.module.css:8:  /* allow: 题号列最小宽度（32px 列表几何） */
apps/web/src/pages/interview/RoomParts.module.css:67:  /* allow: 作答区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:85:  /* allow: 进度条高度（6px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:87:  /* allow: 进度条最小宽度（40px 几何） */
apps/web/src/pages/chat/Composer.module.css:6:  /* allow: 输入区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:6:  /* allow: 二级栏底部分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:69:  /* allow: 会话项发丝边框线宽（1px 几何，选中态复用） */
apps/web/src/pages/chat/SessionSidebar.module.css:124:    /* allow: 会话侧栏固定宽度（260px 版式几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:127:    /* allow: 侧栏右分隔线线宽（1px 几何） */
apps/web/src/pages/chat/MessageBubble.module.css:5:  /* allow: 消息气泡最大宽度（720px 版式几何） */
apps/web/src/pages/chat/MessageBubble.module.css:8:  /* allow: 气泡发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/pages/chat/MessageBubble.module.css:53:  /* allow: 流式光标块固定宽度（8px 几何） */
apps/web/src/pages/chat/MessageBubble.module.css:56:  /* allow: 光标块与文字的固定间距（2px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:50:  /* allow: 上传拖拽区最小高度（96px 组件几何） */
apps/web/src/pages/InterviewIntroPage.module.css:53:  /* allow: 拖拽区发丝虚线线宽（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:62:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:64:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:76:  /* allow: 进度条轨道高度（6px 几何） */
apps/web/src/pages/ChatPage.module.css:26:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/AiSettingsPage.module.css:6:  /* allow: 设置页内容区最大宽度（960px 版式几何） */
apps/web/src/pages/InterviewRoomPage.module.css:14:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewRoomPage.module.css:69:  /* allow: 提示条底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:86:  /* allow: 逐题回放卡发丝边框线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:155:  /* allow: 维度名称列最小宽度（48px 表格列几何） */
apps/web/src/pages/InterviewReportPage.module.css:165:  /* allow: 维度分数列最小宽度（72px 表格列几何） */
~~~

集合核对：与 T1-EVIDENCE §3.8 的 48 条逐条对比，删去 `InterviewReportPage.module.css` 的综合分 42px 一条，其余 47 条的（文件，理由）集合完全相同；三个文件因在其上方新增规则而行号顺移：`SessionSidebar.module.css` 64→69、101→124、104→127；`InterviewReportPage.module.css` 87→86、156→155、166→165。

### 3.2 预留 token 消费归零核对

~~~text
$ for v in br-color-accent-hover br-color-accent-active br-color-accent-muted br-radius-xs br-text-hero; do
    echo "== --$v =="; grep -rn -- "--$v" apps/web/src | grep -v 'styles/tokens.css'; done
== --br-color-accent-hover ==
apps/web/src/components/Button.module.css:39:  background: var(--br-color-accent-hover);
== --br-color-accent-active ==
apps/web/src/components/Button.module.css:43:  background: var(--br-color-accent-active);
== --br-color-accent-muted ==
apps/web/src/components/Badge.module.css:16:  background: var(--br-color-accent-muted);
apps/web/src/components/AppShell.module.css:50:  background: var(--br-color-accent-muted);
apps/web/src/components/AppShell.module.css:54:  background: var(--br-color-accent-muted);
apps/web/src/components/Input.module.css:22:  box-shadow: 0 0 0 var(--br-space-1) var(--br-color-accent-muted);
apps/web/src/components/Select.module.css:21:  box-shadow: 0 0 0 var(--br-space-1) var(--br-color-accent-muted);
apps/web/src/pages/chat/SessionSidebar.module.css:89:  background: var(--br-color-accent-muted);
apps/web/src/pages/chat/SessionSidebar.module.css:95:  background: var(--br-color-accent-muted);
apps/web/src/pages/InterviewIntroPage.module.css:123:  background: var(--br-color-accent-muted);
== --br-radius-xs ==
apps/web/src/components/Badge.module.css:5:  border-radius: var(--br-radius-xs);
apps/web/src/pages/interview/RoomParts.module.css:17:  border-radius: var(--br-radius-xs);
apps/web/src/pages/InterviewReportPage.module.css:105:  border-radius: var(--br-radius-xs);
== --br-text-hero ==
apps/web/src/pages/InterviewReportPage.module.css:48:  font-size: var(--br-text-hero);
~~~

数字：四个预留 token 在 tokens.css 之外均有消费——accent-hover 1 处、accent-active 1 处、accent-muted 8 处、radius-xs 3 处；`--br-text-hero` 消费 1 处。T2 登记为预留、本票落消费点。

### 3.3 交互态清单（元素 → 状态 → 消费 token → 文件:行号）

| 元素 | 状态 | 消费（token） | 文件:行号 |
| --- | --- | --- | --- |
| Button.primary | hover | --br-color-accent-hover | components/Button.module.css:38-39 |
| Button.primary | active | --br-color-accent-active | components/Button.module.css:42-43 |
| Button.secondary | hover | --br-color-surface | components/Button.module.css:52-53 |
| Button.secondary | active | --br-color-surface + --br-color-text-muted | components/Button.module.css:56-58 |
| Button.ghost | hover | --br-color-surface + --br-color-text | components/Button.module.css:66-68 |
| Button.ghost | active | --br-color-border + --br-color-text | components/Button.module.css:71-73 |
| Button（通用过渡） | transition | --br-duration-fast | components/Button.module.css:12-15 |
| Input | hover | --br-color-accent | components/Input.module.css:16-17 |
| Input | focus-visible | --br-color-accent + --br-color-accent-muted + --br-space-1 | components/Input.module.css:20-23 |
| Input（通用过渡） | transition | --br-duration-fast | components/Input.module.css:11-13 |
| Select | hover | --br-color-accent | components/Select.module.css:15-16 |
| Select | focus-visible | --br-color-accent + --br-color-accent-muted + --br-space-1 | components/Select.module.css:19-22 |
| Select（通用过渡） | transition | --br-duration-fast | components/Select.module.css:10-12 |
| AppShell 导航项 | hover | --br-color-surface + --br-color-text | components/AppShell.module.css:44-46 |
| AppShell 导航项 | active | --br-color-accent-muted | components/AppShell.module.css:49-50 |
| AppShell 导航项 | 选中 .navActive | --br-color-accent-muted + --br-color-accent | components/AppShell.module.css:53-54 |
| AppShell 导航项（过渡） | transition | --br-duration-fast | components/AppShell.module.css:39-41 |
| SessionSidebar 会话项 | hover | --br-color-border + --br-color-surface-raised | pages/chat/SessionSidebar.module.css:83-85 |
| SessionSidebar 会话项 | active | --br-color-accent-muted | pages/chat/SessionSidebar.module.css:88-89 |
| SessionSidebar 会话项 | 选中 .active / .active:hover | --br-color-accent + --br-color-accent-muted | pages/chat/SessionSidebar.module.css:92-95 |
| SessionSidebar 会话项（过渡） | transition | --br-duration-fast | pages/chat/SessionSidebar.module.css:78-80 |
| SessionSidebar 删除键 | hover | --br-color-danger | pages/chat/SessionSidebar.module.css:118-119 |
| SessionSidebar 删除键（过渡） | transition | --br-duration-fast | pages/chat/SessionSidebar.module.css:115 |
| SessionSidebar 折叠 summary | hover | --br-color-text | pages/chat/SessionSidebar.module.css:35-36 |
| SessionSidebar 折叠 summary（过渡） | transition | --br-duration-fast | pages/chat/SessionSidebar.module.css:32 |
| 上传页「继续上次面试」行 | hover | --br-color-accent-muted | pages/InterviewIntroPage.module.css:122-123 |
| 上传页「继续上次面试」行（过渡） | transition | --br-duration-fast | pages/InterviewIntroPage.module.css:119 |
| Table 数据行 | hover | --br-color-surface-raised | components/Table.module.css:25-26 |
| Table 数据行（过渡） | transition | --br-duration-fast | components/Table.module.css:22 |
| Badge | 圆角 | --br-radius-xs | components/Badge.module.css:5 |
| 面试间类别徽记 | 圆角 | --br-radius-xs | pages/interview/RoomParts.module.css:17 |
| 报告页类别徽记 | 圆角 | --br-radius-xs | pages/InterviewReportPage.module.css:105 |
| 报告页综合分 | 字阶 | --br-text-hero | pages/InterviewReportPage.module.css:48 |

focus-visible：Button / 导航项 / 会话项沿用全局 `:focus-visible`（base.css:18-22，本票零改动）；Input / Select 在该全局环之上追加 border-color + accent-muted 光晕。

### 3.4 transition 全量读数与 reduced-motion 覆盖

~~~text
$ grep -rn 'transition' apps/web/src
apps/web/src/components/Table.module.css:22:  transition: background var(--br-duration-fast);
apps/web/src/components/Table.module.css:31:    transition: none;
apps/web/src/components/AppShell.module.css:39:  transition:
apps/web/src/components/AppShell.module.css:87:    transition: none;
apps/web/src/components/Button.module.css:12:  transition:
apps/web/src/components/Button.module.css:78:    transition: none;
apps/web/src/components/Collapsible.module.css:40:  transition: transform var(--br-duration-fast);
apps/web/src/components/Collapsible.module.css:49:    transition: none;
apps/web/src/components/Input.module.css:11:  transition:
apps/web/src/components/Input.module.css:27:    transition: none;
apps/web/src/components/Select.module.css:10:  transition:
apps/web/src/components/Select.module.css:26:    transition: none;
apps/web/src/pages/interview/RoomParts.module.css:91:  transition: width var(--br-duration-normal);
apps/web/src/pages/interview/RoomParts.module.css:102:    transition: none;
apps/web/src/pages/chat/SessionSidebar.module.css:32:  transition: color var(--br-duration-fast);
apps/web/src/pages/chat/SessionSidebar.module.css:78:  transition:
apps/web/src/pages/chat/SessionSidebar.module.css:115:  transition: color var(--br-duration-fast);
apps/web/src/pages/chat/SessionSidebar.module.css:149:    transition: none;
apps/web/src/pages/InterviewIntroPage.module.css:87:  transition: width var(--br-duration-fast);
apps/web/src/pages/InterviewIntroPage.module.css:119:  transition: background var(--br-duration-fast);
apps/web/src/pages/InterviewIntroPage.module.css:134:    transition: none;
~~~

本票新增/改写的 transition（9 处声明）与其 reduced-motion 覆盖：

| 动效规则 | 时长 token | reduced-motion 覆盖（同文件、同选择器） |
| --- | --- | --- |
| Button `.button`（background/border-color/color） | --br-duration-fast（120ms） | components/Button.module.css:76-80 `.button { transition: none; }` |
| Input `.input`（border-color/box-shadow） | --br-duration-fast（120ms） | components/Input.module.css:25-29 `.input { transition: none; }` |
| Select `.select`（border-color/box-shadow） | --br-duration-fast（120ms） | components/Select.module.css:24-28 `.select { transition: none; }` |
| AppShell `.navLink`（background/color） | --br-duration-fast（120ms） | components/AppShell.module.css:85-89 `.navLink { transition: none; }` |
| Table `.table tbody tr`（background） | --br-duration-fast（120ms） | components/Table.module.css:29-33 `.table tbody tr { transition: none; }` |
| SessionSidebar `.summary`（color） | --br-duration-fast（120ms） | pages/chat/SessionSidebar.module.css:145-150 `.summary { transition: none; }` |
| SessionSidebar `.session`（background/border-color） | --br-duration-fast（120ms） | pages/chat/SessionSidebar.module.css:145-150 `.session { transition: none; }` |
| SessionSidebar `.delete`（color） | --br-duration-fast（120ms） | pages/chat/SessionSidebar.module.css:145-150 `.delete { transition: none; }` |
| 上传页 `.sessions li`（background） | --br-duration-fast（120ms） | pages/InterviewIntroPage.module.css:131-135 `.sessions li { transition: none; }` |

数字：新增/改写 transition 9 处声明全部为 `var(--br-duration-fast)`（120ms，≤200ms）；无 `ms` 裸值、无 `--br-duration-normal` 的新增；每条都在同文件 reduced-motion 内被同选择器重访。表中未列 `--br-duration-normal` 的 RoomParts `.progressBar` 与 InterviewIntroPage `.bar`，二者为既有过渡，其覆盖块原样保留。

### 3.5 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  186 passed (186)
VITEST_EXIT=0

$ pnpm -C apps/web typecheck
$ tsc --noEmit
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：26 文件 / 186 例全绿，只增不减（纯样式不新增测试）；typecheck 与 lint 退出码 0。

### 3.6 verify --layer all

~~~text
$ bash scripts/verify.sh --layer all
[1/17] cd apps/api && uv run pytest --cov=... → 997 passed, 3 warnings in 87.94s
[2/17] check_coverage_floors.py → floors ok（TOTAL 6553 stmts / 305 miss / 95%）
[3/17] pnpm -C apps/web exec vitest run → 26 passed (26) / 186 passed (186)
[4/17] cd apps/api && uv run ruff check . → All checks passed!
[5/17] cd apps/api && uv run ruff format --check . → 268 files already formatted
[6/17] alembic upgrade head → ok
[7/17] alembic check → No new upgrade operations detected.
[8/17] export_openapi.py --check → openapi.json is up to date
[9/17] extract_api_index.py --check → API index is up to date
[10/17] pnpm -C apps/web lint → exit 0
[11/17] pnpm -C apps/web typecheck → exit 0
[12/17] pnpm -C apps/web check:api → schema.d.ts 无 diff
[13/17] python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
[14/17] ... pytest tests/test_fault_probe.py ... → 101 passed, 2 warnings in 6.98s
[15/17] for f in scripts/*.sh; do bash -n "$f" || exit 1; done → shell syntax ok
[16/17] check_scripts.py → script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[17/17] verify_audit_evidence.py --structural → structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T115357Z-all
~~~

数字：17 条命令全过，末行 ALL PASS，退出码 0；API 997 passed；coverage floors 过（TOTAL 95%）；web 186 passed；契约三件套（openapi / api-index / schema.d.ts）零 diff；守卫绿。

### 3.7 变异证明

锚点取本票新增 token `--br-text-hero` 的定义行，是「定义被删、消费仍在」的真变异（不是媒体查询前缀一类拼写）。

~~~text
$ sha_before=$(sha256sum '/root/better resume/apps/web/src/styles/tokens.css' | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh --test 'python3 scripts/check_web_style_guards.py' \
    --file '/root/better resume/apps/web/src/styles/tokens.css' \
    --find '  --br-text-hero: 42px;' --replace ''; echo MUT_EXIT=$?
== 1/3 baseline: the test must PASS on the untouched implementation ==
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)

== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/styles/tokens.css ==
mutated 1 occurrence in /root/better resume/apps/web/src/styles/tokens.css

== 2/3 red: the test must FAIL on the mutated implementation ==
pages/InterviewReportPage.module.css:48: G1 --br-text-hero 被引用但没有定义（守卫① token 零假变量）
check_web_style_guards: 1 violation(s)
ok: mutation was caught

== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/styles/tokens.css sha256=e91d300e4e70ceff…
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)

PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/styles/tokens.css)
MUT_EXIT=0
sha_after=e91d300e4e70ceff6f70f4fa9ef4d26fc577472caa614ac25fc9089ebdfb05f0
CMP_OK
~~~

数字：基线绿 → 变异红（G1 点名 `pages/InterviewReportPage.module.css:48`）→ 恢复绿；恢复后 sha256 与变异前同为 `e91d300e4e70ceff6f70f4fa9ef4d26fc577472caa614ac25fc9089ebdfb05f0`，`cmp` 逐字节相同；`--file` 用绝对路径。

### 3.8 改动面自查

~~~text
$ git status --porcelain
 M apps/web/src/components/AppShell.module.css
 M apps/web/src/components/Badge.module.css
 M apps/web/src/components/Button.module.css
 M apps/web/src/components/Input.module.css
 M apps/web/src/components/Select.module.css
 M apps/web/src/components/Table.module.css
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/styles/tokens.css
?? docs/tickets/p14-web-redesign/T10-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T10-visual-polish.md

$ git diff --numstat
13	0	apps/web/src/components/AppShell.module.css
1	1	apps/web/src/components/Badge.module.css
27	1	apps/web/src/components/Button.module.css
14	0	apps/web/src/components/Input.module.css
14	0	apps/web/src/components/Select.module.css
14	0	apps/web/src/components/Table.module.css
8	1	apps/web/src/pages/InterviewIntroPage.module.css
2	3	apps/web/src/pages/InterviewReportPage.module.css
32	1	apps/web/src/pages/chat/SessionSidebar.module.css
1	1	apps/web/src/pages/interview/RoomParts.module.css
1	0	apps/web/src/styles/tokens.css
~~~

逐文件说明：

- `apps/web/src/styles/tokens.css`（+1）：仅新增 `--br-text-hero: 42px;` 一行。
- `apps/web/src/pages/InterviewReportPage.module.css`（+2 −3）：`.overall` 的 42px 改 `var(--br-text-hero)` 并删 allow 行；`.badge` 圆角改 `--br-radius-xs`。
- `apps/web/src/components/Button.module.css`（+27 −1）：`.button` 过渡加 color；primary/secondary/ghost 的 hover/active。
- `apps/web/src/components/Input.module.css` / `Select.module.css`（各 +14）：过渡、hover、focus-visible、reduced-motion。
- `apps/web/src/components/Table.module.css`（+14）：数据行 hover + 过渡 + reduced-motion。
- `apps/web/src/components/AppShell.module.css`（+13）：导航项过渡、`:active`、reduced-motion。
- `apps/web/src/components/Badge.module.css`（+1 −1）：圆角 pill → `--br-radius-xs`。
- `apps/web/src/pages/chat/SessionSidebar.module.css`（+32 −1）：会话项 hover/active/选中、删除键与 summary hover、过渡与 reduced-motion。
- `apps/web/src/pages/InterviewIntroPage.module.css`（+8 −1）：「继续上次面试」行 hover、过渡、reduced-motion 补充选择器。
- `apps/web/src/pages/interview/RoomParts.module.css`（+1 −1）：类别徽记圆角改 `--br-radius-xs`。
- `docs/tickets/p14-web-redesign/T10-visual-polish.md`（新建，未跟踪）：本票票面；`T10-EVIDENCE.md`（本文件，新建）。

未触碰：任何 TSX/TS、`styles/base.css`、`scripts/check_web_style_guards.py`、`apps/api/tests/test_web_style_guards.py`、`scripts/verify.sh`、`src/api`、`src/audio`、`src/stream`、`pages/chat/Composer.tsx`、README、T1–T3 票与 EVIDENCE、T4–T9 票；无新依赖；无 commit。

## 四、未验证项诚实清单

- 浏览器观感与手感（hover/active 的即时反馈、accent-muted 弱背景的可见度、focus 光晕与全局 2px 外框叠加后的观感、Badge 由 pill 改 2px 圆角后的视觉效果）AI 无浏览器与截图能力，未人工核验。
- 深色主题下各交互态（尤其 `--br-color-accent-muted` 在深色底上的弱背景与光晕）未人工核对；本票只保证引用的 token 在深色块有定义（G1b 静态校验）。
- `box-shadow` 光晕宽度取 `var(--br-space-1)`（4px），是执行方在「不写裸 px」约束下的取值选择；缩放/高 DPI 下的观感未核。
- Badge 圆角由 pill 改为 `--br-radius-xs`（2px）后的视觉统一性只有静态读数，未获页面批确认。
- Table 行 hover 与上传页行 hover 在窄屏、长文本下的表现未核。
- 未跑 `bash scripts/compose_smoke.sh`（README §4.3 回归底线之一）；本票未改部署面与构建产物，缓存头与 bundle hash 未核。
- MANUAL-TESTING §1.1–1.4 的实时转写 / 答题交互未手测；本票未改 Composer 与 audio 逻辑。
- 无视觉快照测试（本阶段明确不引）；jsdom 不应用媒体查询与伪类，交互态只有静态存在性与 G4 机器兜底。

## 五、与提案的偏差

1. 除 Badge 组件外，同类小徽记（`RoomParts.module.css` 与 `InterviewReportPage.module.css` 的 `.badge`）也改用 `--br-radius-xs`，以保证同类徽记圆角一致；未扩到卡片 / 按钮 / 输入控件。
2. Input / Select 的 focus 强化采用「border-color accent + 4px accent-muted 光晕」，在全局 `:focus-visible` 外框之外叠加，未替换、未削弱全局环（base.css 零改动）。
3. ghost 的 `:active` 以 `--br-color-border` 作按下底色（既有 border 系 token）；本批要求「secondary/ghost 用 surface/text-muted 系」，此处用 border 系作按下反馈，取「既有 token 内的最近中性档」，未引入新色值。
4. 上传页「继续上次面试」行 hover 用 `--br-color-accent-muted` 弱背景而非 surface 系，理由是行位于 surface 底色的 Card 内、surface 系看不出变化；该 token 的用途限定为 hover / 选中弱背景，符合本批口径。
5. 未新增任何 allow；白名单由 48 降到 47，唯一删项即本票要清理的综合分 42px。
6. 新增 transition 全部取 `--br-duration-fast`（120ms），未使用 `--br-duration-normal`；本批要求二者皆可，取更短的一档以贴合「状态反馈」而非「进场」。
