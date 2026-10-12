# P14-T2 验收包 — 视觉 token 扩充（靛蓝色阶 / 渐变 / 阴影层级）

- 票据：docs/tickets/p14-web-redesign/T2-visual-tokens.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.5 / §4.1 / §4.3；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

T2 只在 token 层完成「产品工具风 + Linear 细节」的体系扩充：

1. accent 由单值扩成靛蓝（indigo）色阶：主色 / hover / active / 弱化，主名沿用 --br-color-accent。
2. 新增三个点缀渐变 token：hero / 综合分 / 类别徽章，只在页面批按点缀使用，不铺大面。
3. 阴影覆盖 卡片 / 浮层 / 吸底 三级；圆角做微调、间距做补档。
4. 所有 --br-color-* / --br-gradient-* / --br-shadow-* 在 :root 定义的 token 同步给出 prefers-color-scheme: dark 定义，满足守卫①的深浅双定义。
5. 交可复跑读数、未验证项与偏差；不碰 TS/TSX、REST 契约、依赖、webfont，也不做组件样式（T3）与页面版式（T4–T8）。

## 二、实现决定交代

### 2.1 靛蓝 accent 色阶取值

| 语义 | token | 浅色 | 深色 | 依据 |
| --- | --- | --- | --- | --- |
| 主色 | --br-color-accent | #4f46e5 | #818cf8 | 靛蓝 600 / 400；浅色承担按钮底与文字强调，深色用更亮一档保证在 #0f1115 上可读 |
| hover | --br-color-accent-hover | #4338ca | #a5b4fc | 靛蓝 700 / 300；浅色交互压深，深色交互提亮 |
| active | --br-color-accent-active | #3730a3 | #c7d2fe | 靛蓝 800 / 200；active 比 hover 再深 / 再亮一档，保持同向递进 |
| 弱化 | --br-color-accent-muted | #eef2ff | #312e81 | 靛蓝 50 / 900；作为弱化填充（徽章底、柔和强调块），与浅色底、深色底都保持低对比 |
| 反色 | --br-color-accent-contrast | #ffffff | #0f1115 | 沿用既有取值，主色上的文字色 |

- 全部落在靛蓝同色相，未换色系、未引 webfont；--br-color-accent 继续作为唯一主名，不另造 --br-color-primary 之类重复语义。

### 2.2 渐变 token 取值

| token | 浅色 | 深色 |
| --- | --- | --- |
| --br-gradient-hero | linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) | linear-gradient(135deg, #4f46e5 0%, #3730a3 100%) |
| --br-gradient-score | linear-gradient(120deg, #4f46e5 0%, #6366f1 100%) | linear-gradient(120deg, #818cf8 0%, #a5b4fc 100%) |
| --br-gradient-badge | linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%) | linear-gradient(135deg, #312e81 0%, #3730a3 100%) |

- 三处对应票据点名的 hero / 综合分 / 类别徽章；色相限定在靛蓝 200–600 / 100–900 内，不引入第二色相。
- 本票没有页面可挂载这三处，故按「预留槽位」登记（见 §3.5），不静默留无主 token。

### 2.3 阴影层级

- 沿用既有主名：--br-shadow-sm 承担「卡片」（Card.module.css:11 的 .raised 是其消费点），--br-shadow-md 承担「浮层」。
- 新增 --br-shadow-sticky（0 -4px 16px）承担「吸底」，负 Y 偏移向内容区上方投影；浅色 rgb(15 23 42 / 10%)、深色 rgb(0 0 0 / 50%)，与既有两级同一克制档。
- 不把 sm/md 改名为 card/overlay：票面拍死「以保留现有语义名为主名」，映射关系写进 tokens.css 注释与本节。

### 2.4 圆角 / 字阶 / 间距

- 圆角微调：新增 --br-radius-xs: 2px，作为档位中最细的一档，供 T3 的小控件（徽章、输入内元素）使用；既有 sm/md/lg/pill 取值不动，避免页面批前产生全局几何位移。
- 字阶：未新增、未改值。票面禁改字号语义档位，且改字号会牵动页面版式（T4–T8）；现有 xs/sm/md/lg/xl 五档覆盖全部 var() 消费点。T1 已把报告页综合分 42px 记为待页面批裁定，本票不抢跑。
- 间距补档：新增 --br-space-7: 40px，补上 32px（space-6）与 48/72/96px 这类几何 allow 之间的空档。

### 2.5 深色对齐

- 新增的 3 个 color、3 个 gradient、1 个 shadow token 均在 @media (prefers-color-scheme: dark) 的 :root 块重述（守卫① G1b 静态校验）；本票的深浅配对在 §3.1 与 §3.2 有读数与变异证明。
- radius-xs / space-7 / font / text / leading / duration / z 非主题依赖，无需深色重述。

### 2.6 消费点与旧名处置口径

- 未改名、未删除任何既有 token：37 个既有名字全部保留为主名（逐个读数与处置见 §3.3）。因此 apps/web/src/**/*.module.css 不需要任何替换，本票在该路径上零改动。
- accent 的「消费点迁移」集中在 token 本身：--br-color-accent 取靛蓝后，其 15 处 var() 消费点（Button.primary、MessageBubble.streaming、RadarChart 等）自动渲染靛蓝，无需逐文件改；不存在别名层。
- 既有非本票引入的无消费点 token（--br-radius-sm、--br-shadow-md、--br-z-overlay）保持原样，登记为既有预留；本票不顺手删除，避免越界。
- 新增的 hover/active/muted、三个渐变、shadow-sticky、radius-xs、space-7 在本票无消费点，全部按票据允许的「预留槽位」登记，并写明预计消费票（§3.5）。

### 2.7 守卫与变异

- 守卫①：新增主题依赖 token 的深浅双定义由 scripts/check_web_style_guards.py 静态校验（§3.1）。
- 变异证明：删掉 dark 块里 --br-color-accent-hover 一行，守卫①点名该 token 深色缺定义（§3.2），证明新 token 被守卫真实钉住，而非「恒绿检查」。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行，前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
~~~

### 3.1 守卫脚本

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
EXIT=0
~~~

数字：退出码 0；扫描 21 个 .css；违规 0 条；末行 check_web_style_guards: ok。

### 3.2 深浅双定义变异证明

锚点取新增 token --br-color-accent-hover 的深色定义行；这是真变异（删的是 token 定义本身，不是 @media 前缀的拼写）。

~~~text
$ sha_before=$(sha256sum apps/web/src/styles/tokens.css | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh --test 'python3 scripts/check_web_style_guards.py' \
    --file '/root/better resume/apps/web/src/styles/tokens.css' \
    --find '    --br-color-accent-hover: #a5b4fc;' --replace ''; echo MUT_EXIT=$?
== 1/3 baseline: the test must PASS on the untouched implementation ==
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/styles/tokens.css ==
mutated 1 occurrence in /root/better resume/apps/web/src/styles/tokens.css
== 2/3 red: the test must FAIL on the mutated implementation ==
styles/tokens.css:15: G1 --br-color-accent-hover 深色块缺定义（守卫① 深浅双定义）
check_web_style_guards: 1 violation(s)
ok: mutation was caught
== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/styles/tokens.css sha256=062a3de69a295f87…
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/styles/tokens.css)
MUT_EXIT=0
$ sha_after=$(sha256sum apps/web/src/styles/tokens.css | cut -d' ' -f1)
sha_before=062a3de69a295f87b90d22da65c2eb4fde193d6ec588fec0540c9fb891810b37
sha_after=062a3de69a295f87b90d22da65c2eb4fde193d6ec588fec0540c9fb891810b37
~~~

数字：基线绿 → 变异红（G1 点名 styles/tokens.css:15）→ 恢复绿；恢复后 sha256 与变异前逐字节一致（同一 hash）；--file 用绝对路径。

### 3.3 既有 token 逐个 grep 读数与处置

命令：grep -rn -- '<旧名>' apps/web/src | wc -l（逐名一条）；「var() 消费点」是同一棵树上 var(--br-<名>) 的精确出现次数，用于区分前缀同名（如 --br-color-text 会匹配到 --br-color-text-muted 的行）。本票未改任何 module.css，因此 var() 消费数与 T1 收口状态一致。

| 既有 token | grep 读数 | var() 消费点 | 深浅定义 | 处置 |
| --- | --- | --- | --- | --- |
| --br-color-bg | 5 | 3 | 2 | 保留 |
| --br-color-surface | 19 | 8 | 2 | 保留 |
| --br-color-surface-raised | 9 | 7 | 2 | 保留 |
| --br-color-border | 21 | 19 | 2 | 保留 |
| --br-color-text | 45 | 8 | 2 | 保留（grep 读数含 --br-color-text-muted 的前缀行） |
| --br-color-text-muted | 35 | 33 | 2 | 保留 |
| --br-color-accent | 26 | 15 | 2 | 保留为主名；值取靛蓝阶（§2.1）；grep 读数含 hover/active/muted/contrast 前缀行 |
| --br-color-accent-contrast | 3 | 1 | 2 | 保留 |
| --br-color-danger | 14 | 8 | 2 | 保留 |
| --br-color-danger-surface | 4 | 2 | 2 | 保留 |
| --br-color-success | 3 | 1 | 2 | 保留 |
| --br-color-warning | 8 | 2 | 2 | 保留（T1 补定）；读数含 warning-bg 前缀行 |
| --br-color-warning-bg | 4 | 2 | 2 | 保留（T1 补定） |
| --br-space-1 | 11 | 10 | 1 | 保留 |
| --br-space-2 | 35 | 34 | 1 | 保留 |
| --br-space-3 | 39 | 39 | 1 | 保留 |
| --br-space-4 | 26 | 27 | 1 | 保留（有行内一次写两个 var，grep 行数少于出现次数） |
| --br-space-5 | 11 | 10 | 1 | 保留 |
| --br-space-6 | 5 | 4 | 1 | 保留 |
| --br-radius-sm | 1 | 0 | 1 | 保留（既有预留，本票未引入） |
| --br-radius-md | 8 | 7 | 1 | 保留 |
| --br-radius-lg | 6 | 5 | 1 | 保留 |
| --br-radius-pill | 6 | 5 | 1 | 保留 |
| --br-font-sans | 2 | 1 | 1 | 保留 |
| --br-font-mono | 6 | 5 | 1 | 保留 |
| --br-text-xs | 8 | 7 | 1 | 保留 |
| --br-text-sm | 34 | 33 | 1 | 保留 |
| --br-text-md | 8 | 7 | 1 | 保留 |
| --br-text-lg | 11 | 10 | 1 | 保留 |
| --br-text-xl | 3 | 2 | 1 | 保留 |
| --br-leading-tight | 3 | 2 | 1 | 保留 |
| --br-leading-normal | 3 | 2 | 1 | 保留 |
| --br-shadow-sm | 3 | 1 | 2 | 保留（卡片级，Card.module.css:11 消费） |
| --br-shadow-md | 2 | 0 | 2 | 保留（浮层级，既有预留） |
| --br-duration-fast | 4 | 4 | 1 | 保留 |
| --br-duration-normal | 2 | 1 | 1 | 保留 |
| --br-z-overlay | 1 | 0 | 1 | 保留（既有预留，本票未引入） |

数字：既有 token 37 个，改名 0、删除 0、保留 37；因无删除名，「删除名 grep 归零」的检查集合为空。保留名的别名兼容说明：全部继续作为唯一主名使用，消费点写法不变，无别名层；--br-color-accent 值取靛蓝后所有消费点自动生效。

### 3.4 allow 白名单

~~~text
$ grep -rn 'allow:' apps/web/src | wc -l
44
~~~

逐条（文件:行号 — 理由，均位于违规行上一行）：

~~~text
apps/web/src/styles/base.css:19:  /* allow: 键盘焦点外框线宽（2px 几何） */
apps/web/src/styles/base.css:21:  /* allow: 焦点外框与控件的偏移（2px 几何） */
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
apps/web/src/components/Empty.module.css:7:  /* allow: 空态占位框发丝虚线线宽（1px 几何） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:38:  /* allow: 题号列最小宽度（24px 列表几何） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:73:  /* allow: 降级提示左侧警示条宽度（3px 几何） */
apps/web/src/pages/interview/RadarChart.module.css:7:  /* allow: 雷达图画布最大宽度（260px 画布尺寸） */
apps/web/src/pages/interview/RadarChart.module.css:35:  /* allow: 雷达图轴标签字号（9px，随画布缩放） */
apps/web/src/pages/interview/RoomParts.module.css:8:  /* allow: 题号列最小宽度（32px 列表几何） */
apps/web/src/pages/interview/RoomParts.module.css:67:  /* allow: 作答区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:85:  /* allow: 进度条高度（6px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:87:  /* allow: 进度条最小宽度（40px 几何） */
apps/web/src/pages/chat/Composer.module.css:6:  /* allow: 输入区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:5:  /* allow: 会话侧栏固定宽度（260px 版式几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:8:  /* allow: 侧栏右分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:47:  /* allow: 会话项发丝边框线宽（1px 几何，选中态复用） */
apps/web/src/pages/chat/MessageBubble.module.css:5:  /* allow: 消息气泡最大宽度（720px 版式几何） */
apps/web/src/pages/chat/MessageBubble.module.css:8:  /* allow: 气泡发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/pages/chat/MessageBubble.module.css:53:  /* allow: 流式光标块固定宽度（8px 几何） */
apps/web/src/pages/chat/MessageBubble.module.css:56:  /* allow: 光标块与文字的固定间距（2px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:49:  /* allow: 上传拖拽区最小高度（96px 组件几何） */
apps/web/src/pages/InterviewIntroPage.module.css:52:  /* allow: 拖拽区发丝虚线线宽（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:61:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:63:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:75:  /* allow: 进度条轨道高度（6px 几何） */
apps/web/src/pages/ChatPage.module.css:19:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/AiSettingsPage.module.css:6:  /* allow: 设置页内容区最大宽度（960px 版式几何） */
apps/web/src/pages/AiSettingsPage.module.css:38:  /* allow: 表格行底分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewRoomPage.module.css:14:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewRoomPage.module.css:63:  /* allow: 提示条底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:42:  /* allow: 综合分英雄数字的一次性展示字号（超出 --br-text-* 字阶，非间距/常规字阶） */
apps/web/src/pages/InterviewReportPage.module.css:81:  /* allow: 逐题回放卡发丝边框线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:150:  /* allow: 维度名称列最小宽度（48px 表格列几何） */
apps/web/src/pages/InterviewReportPage.module.css:160:  /* allow: 维度分数列最小宽度（72px 表格列几何） */
~~~

数字：实测 44 条；上面逐条与实际 grep 输出集合完全一致（差异条数 0）。本票新增 allow 0 条（白名单维持 44），未走 token 的放行全部是几何类。

### 3.5 新 token 清单表

新增 9 个 token（既有 --br-color-accent 是同名值迁移，不重复计入；token 总数由 37 增至 46）。

| 新 token | 浅色值 | 深色值 | 消费点 / 预留槽位 |
| --- | --- | --- | --- |
| --br-color-accent-hover | #4338ca | #a5b4fc | 预留：T3 按钮 / 输入 / 会话项 hover 态 |
| --br-color-accent-active | #3730a3 | #c7d2fe | 预留：T3 按钮 / 会话项 active 态 |
| --br-color-accent-muted | #eef2ff | #312e81 | 预留：T3/T4/T8 徽章底与弱化强调块 |
| --br-gradient-hero | linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) | linear-gradient(135deg, #4f46e5 0%, #3730a3 100%) | 预留：T4 报告 hero / T5 上传页主视觉 |
| --br-gradient-score | linear-gradient(120deg, #4f46e5 0%, #6366f1 100%) | linear-gradient(120deg, #818cf8 0%, #a5b4fc 100%) | 预留：T4 报告页综合分 |
| --br-gradient-badge | linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%) | linear-gradient(135deg, #312e81 0%, #3730a3 100%) | 预留：T4/T6 类别徽章 |
| --br-shadow-sticky | 0 -4px 16px rgb(15 23 42 / 10%) | 0 -4px 16px rgb(0 0 0 / 50%) | 预留：T6/T7 composer 吸底 |
| --br-radius-xs | 2px | 非主题依赖 | 预留：T3 小控件圆角 |
| --br-space-7 | 40px | 非主题依赖 | 预留：T4–T8 区块间距补档 |

数字：新 token 9 个；票据槽位为 accent 4（含既有主名，新 3）+ 渐变 3 + 阴影 3（新 1）+ 圆角微调与间距补档各 1，总数未超槽位。9 个新 token 均在 tokens.css 有定义行；主题依赖的 7 个（3 color + 3 gradient + 1 shadow）在深色块重述（守卫①通过）。

### 3.6 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  25 passed (25)
      Tests  183 passed (183)
$ pnpm -C apps/web typecheck
$ tsc --noEmit
TYPECHECK_EXIT=0
$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：25 文件 / 183 例全绿，只增不减（README §1.2 记 172 为旧数，T1 实测亦 183）；typecheck 与 lint 退出码 0。本票未增删任何前端测试。

### 3.7 verify --layer all

~~~text
$ bash scripts/verify.sh --layer all
[1/17] cd apps/api && uv run pytest ... → 990 passed, 3 warnings in 94.00s
[2/17] check_coverage_floors.py → floors ok（TOTAL 95%，deep-module 各项达下限）
[3/17] pnpm -C apps/web exec vitest run → 25 passed (25) / 183 passed (183)
[4/17] cd apps/api && uv run ruff check . → All checks passed!
[5/17] cd apps/api && uv run ruff format --check . → 268 files already formatted
[6/17] alembic upgrade head → ok
[7/17] alembic check → No new upgrade operations detected.
[8/17] export_openapi.py --check → openapi.json is up to date
[9/17] extract_api_index.py --check → API index is up to date
[10/17] pnpm -C apps/web lint → exit 0
[11/17] pnpm -C apps/web typecheck → exit 0
[12/17] pnpm -C apps/web check:api → src/api/schema.d.ts 无 diff
[13/17] python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
[14/17] ... pytest tests/test_fault_probe.py ... → 94 passed, 2 warnings in 7.54s
[15/17] for f in scripts/*.sh; do bash -n "$f" || exit 1; done → shell syntax ok
[16/17] check_scripts.py → script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[17/17] verify_audit_evidence.py --structural → structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T065939Z-all
VERIFY_ALL_EXIT=0
~~~

数字：17 条命令全过，末行 ALL PASS，退出码 0；API 990 passed；coverage floors ok（TOTAL 95%）；web 183 passed；守卫绿。

### 3.8 改动面自查

~~~text
=== git status --porcelain ===
 M apps/web/src/components/Button.module.css
 M apps/web/src/components/Card.module.css
 M apps/web/src/components/Collapsible.module.css
 M apps/web/src/components/Empty.module.css
 M apps/web/src/components/Spinner.module.css
 M apps/web/src/components/Textarea.module.css
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/MessageBubble.module.css
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/styles/base.css
 M apps/web/src/styles/tokens.css
 M scripts/verify.sh
?? apps/api/tests/test_web_style_guards.py
?? docs/tickets/p14-web-redesign/T1-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T2-EVIDENCE.md
?? scripts/check_web_style_guards.py
~~~

~~~text
=== git diff --numstat ===
1	0	apps/web/src/components/Button.module.css
1	0	apps/web/src/components/Card.module.css
5	0	apps/web/src/components/Collapsible.module.css
1	0	apps/web/src/components/Empty.module.css
3	0	apps/web/src/components/Spinner.module.css
1	0	apps/web/src/components/Textarea.module.css
18	16	apps/web/src/pages/AiSettingsPage.module.css
1	0	apps/web/src/pages/ChatPage.module.css
5	0	apps/web/src/pages/InterviewIntroPage.module.css
5	1	apps/web/src/pages/InterviewReportPage.module.css
3	1	apps/web/src/pages/InterviewRoomPage.module.css
1	0	apps/web/src/pages/chat/Composer.module.css
10	0	apps/web/src/pages/chat/MessageBubble.module.css
3	0	apps/web/src/pages/chat/SessionSidebar.module.css
2	0	apps/web/src/pages/interview/RadarChart.module.css
4	2	apps/web/src/pages/interview/ResumePreviewCard.module.css
5	1	apps/web/src/pages/interview/RoomParts.module.css
2	0	apps/web/src/styles/base.css
30	2	apps/web/src/styles/tokens.css
2	1	scripts/verify.sh
~~~

逐文件说明：

- apps/web/src/styles/tokens.css：本票唯一实质写入文件。新增靛蓝 accent 阶 3 个、渐变 3 个、--br-shadow-sticky、--br-radius-xs、--br-space-7；--br-color-accent 同名取靛蓝值；新增三个分组注释；深浅两套定义。工作区里该文件同时承载 T1 已落盘的 --br-color-warning/--br-color-warning-bg 与 --br-shadow-sm/--br-shadow-md 的深色定义（T1 未提交），故 diff 读数大于本票净增行数；本票未回退 T1 内容。
- docs/tickets/p14-web-redesign/T2-EVIDENCE.md：本验收包（新建）。
- 其余出现在 git status 的文件均为 T1 的未提交改动（组件 / 页面 module.css、base.css、scripts/verify.sh、两个未跟踪的守卫脚本与测试），本票未触碰；module.css 路径在本票零改动。

## 四、未验证项诚实清单

- 浏览器视觉观感（浅色与深色下靛蓝阶的对比、三个渐变的观感、吸底阴影方向、弱化底的可读性）AI 无浏览器与截图能力，未验证。
- 三个渐变 token、accent hover/active/muted、shadow-sticky、radius-xs、space-7 在本票无消费点，属预留；它们在 T3–T8 落地后的实际视觉与交互未验证。
- prefers-color-scheme 真机切换下的成对取值未人工核对；本票只做了守卫①的静态深色配对校验与一次变异证明。
- 未跑 bash scripts/compose_smoke.sh（README §4.3 的回归底线之一）；本票未改部署面与前端构建产物，缓存头与 bundle hash 未核。verify --layer all 不覆盖 compose。
- 靛蓝取值与 Linear 真实质感的接近程度属主观判断，不作为证据。
- T1 遗留的 42px 英雄字号与 6px/2px 近似映射未在本票复验。

## 五、与提案的偏差

1. 阴影命名保留 --br-shadow-sm（卡片）/ --br-shadow-md（浮层）为主名，新增 --br-shadow-sticky 覆盖吸底；未改成 --br-shadow-card / --br-shadow-overlay。理由是票面拍死「以保留现有语义名为主名」。若页面批更倾向角色名，请在 T3/T4 指定后统一改名。
2. --br-radius-xs（2px）与 --br-space-7（40px）的具体取值由执行方按现有步长最小补档选定，票据只写「圆角微调 / 间距补档」未给档位与数值；请确认这两个取值。
3. 字阶未新增、未改值：票面禁改字号语义档位，且字号牵动页面版式（T4–T8）；「字阶微调」在本票落成「维持现有五档」，如需 hero 大字号请在 T4 与 T1 遗留的 42px allow 一并裁定。
4. 本票未改任何 module.css，也未新增任何 allow（白名单维持 44 条）；「消费点迁移」体现为 --br-color-accent 的集中值迁移，而非逐文件替换。
5. 9 个新 token 全部无本票消费点，按「预留槽位」登记，预计消费票见 §3.5；若要求在 T2 内接入消费点，需要把 T3 的组件样式提前，超出本票「不做组件样式」的边界。
