# P14-T3 验收包 — 页壳 + 两档响应式 + 样式化组件 + 守卫③⑤

- 票据：docs/tickets/p14-web-redesign/T3-shell-and-components.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.2 / §1.4 / §4.1 / §4.3；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

本票是基建批最后一张票，只做「页壳 + 两档响应式 + 样式化组件补齐 + 守卫③⑤」，不做页面内部版式（T4–T8）：

1. **页壳**：AppShell 顶栏（产品名 better-resume + 主导航「对话 / 面试 / AI 设置」+ 右上用户区与退出）+ 居中内容容器（max-width ≈ 1200）；聊天页会话侧栏降为页内二级栏；页内 header 收敛为标题行。
2. **两档响应式**：断点值 1024px；≥1024 双栏照旧；<1024 两列塌单列、二级栏顶部折叠。
3. **样式化组件**：Select / Input / Table / Badge / Skeleton；Select / Input / Table 替换全部 6 处裸控件（ChatPage 的模型 select；InterviewIntroPage 的面试侧重 select 与 file input；AiSettingsPage 的 table / select / input）。Badge / Skeleton 为本票组件补齐交付物，允许无页面消费点。
4. **守卫③⑤**：G3 = 全 CSS 树至少 1 条宽度媒体查询；G5 = apps/web/src/pages/**/*.tsx（排除 *.test.tsx）逐字不得出现裸 <select / <input / <table 标签开头，命中报文件 + 行号 + 条款号。
5. 退出行为与既有 ChatPage 退出等价：api.logout() 成功后 queryClient.invalidateQueries()。

不做：业务逻辑与数据流、TanStack Query / zustand 用法、路由表、REST 契约、依赖、页面内部版式、转写合并语义；不改 docs/tickets/p14-web-redesign 既有文件（只新建本文件）。

## 二、实现决定交代

### 2.1 页壳结构

- App.tsx 在 BrowserRouter 内用 AppShell 包住 Routes；ApiProvider / QueryClientProvider 层级不变。
- AppShell.tsx：顶栏 + 内容容器。主导航常量只指向既有路由 /chat、/interview、/settings/ai；isActive(pathname, to) = pathname 等于 to 或以 to + "/" 开头，因此 /chat/:sessionId 与 /interview/room|report/:id 也会高亮所属区。
- 导航项用 react-router 的 Link + 显式 aria-current="page"（未用 NavLink 内建高亮，以便变异证明能真删到属性），选中态同时挂 .navActive 类做视觉呈现。
- 用户区：已认证时显示 principal.user_id 与「退出」按钮；退出 = api.logout() 成功后 queryClient.invalidateQueries()，与 ChatPage 既有退出路径等价。未认证时隐藏用户区，顶栏仍然渲染。
- 内容容器 .content：flex: 1、max-width: var(--br-width-content)（新增 token，1200px）、margin: 0 auto；≥1024 增加水平内边距。
- 页内标题行：页内 h1 全部降为 h2（唯一 h1 是顶栏品牌 better-resume）；页内跨页导航（返回对话 / AI 设置 / 退出）移除，由顶栏承担。

### 2.2 断点档位

- 唯一档位 1024px，统一写 @media (min-width: 1024px)：窄屏为默认单列，达标后恢复双列（页面栅格）与左侧定宽列（会话二级栏）。
- 落点：AppShell.module.css（内容容器水平内边距）、ChatPage.module.css（.page 纵向 ↔ 横向）、SessionSidebar.module.css（顶部折叠条 ↔ 260px 左列）、InterviewIntroPage.module.css（.grid）、InterviewRoomPage.module.css（.body）、InterviewReportPage.module.css（.grid）。
- 二级栏顶部折叠：SessionSidebar 的会话列表包在原生 <details> / <summary>，窄屏默认收起、点击展开；≥1024 隐藏 summary，并用作者样式覆盖浏览器对已收起 details 的隐藏规则，使列表始终展示为竖列。该交互靠浏览器原生行为，无 JS 状态。

### 2.3 组件 API（全部从 components/index.ts 导出）

| 组件 | 类型 | 说明 |
| --- | --- | --- |
| Select | SelectHTMLAttributes<HTMLSelectElement> | props（value / onChange / aria-label / disabled / children）原样透传，渲染原生 <select> |
| Input | InputHTMLAttributes<HTMLInputElement> | props（value / onChange / type / aria-label / disabled）原样透传，渲染原生 <input>；type="file" 时 event.target.files 语义不变 |
| Table | TableHTMLAttributes<HTMLTableElement> + children | 只给 <table> 套样式；thead / tbody / tr / th / td 结构由调用方原样提供 |
| Badge | { tone?: neutral \| accent \| success \| warning \| danger; children } | 五档语义色全部取自 token；本票无页面消费 |
| Skeleton | { loading; label?; lines?; children } | loading 时渲染 role="status" aria-label 占位，否则渲染 children；本票无页面消费 |

### 2.4 等价替换逐处说明（行号为替换前位置）

| # | 原位置 | 替换 | 语义保持点 |
| --- | --- | --- | --- |
| 1 | AiSettingsPage.tsx:88 <table className={styles.table}> | <Table> | thead / tbody / tr / th / td 结构原样；原页面 .table 样式移入 Table.module.css |
| 2 | AiSettingsPage.tsx:109 <select aria-label="{scene.label} 供应商"> | <Select> | value / onChange / options / aria-label 原样；测试对 HTMLSelectElement.options 的断言不变 |
| 3 | AiSettingsPage.tsx:127 <input aria-label="{scene.label} 目标"> | <Input> | value / onChange / aria-label 原样 |
| 4 | ChatPage.tsx:118 <select aria-label="选择模型"> | <Select> | value / onChange / options（含 disabled 未配置项）原样 |
| 5 | InterviewIntroPage.tsx:72 <select aria-label="面试侧重"> | <Select> | value / onChange / INTERVIEW_TYPE_OPTIONS 原样 |
| 6 | InterviewIntroPage.tsx:88 <input type="file" aria-label="选择简历 PDF"> | <Input type="file"> | event.target.files?.[0] 原样；.dropzone input 元素选择器仍命中该原生 input |

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行，前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
~~~

### 3.1 守卫③⑤先红（G3/G5 规则已落地、断点与控件替换尚未做时的真实树）

~~~
$ python3 scripts/check_web_style_guards.py
G3 全 CSS 树没有宽度断点（至少一条 min-width / max-width 媒体查询）（守卫③）
pages/AiSettingsPage.tsx:88: G5 页面直接使用原生 <table> 标签，请改用样式化组件（守卫⑤）
pages/AiSettingsPage.tsx:109: G5 页面直接使用原生 <select> 标签，请改用样式化组件（守卫⑤）
pages/AiSettingsPage.tsx:127: G5 页面直接使用原生 <input> 标签，请改用样式化组件（守卫⑤）
pages/ChatPage.tsx:118: G5 页面直接使用原生 <select> 标签，请改用样式化组件（守卫⑤）
pages/InterviewIntroPage.tsx:72: G5 页面直接使用原生 <select> 标签，请改用样式化组件（守卫⑤）
pages/InterviewIntroPage.tsx:88: G5 页面直接使用原生 <input> 标签，请改用样式化组件（守卫⑤）
check_web_style_guards: 7 violation(s)
GUARD_EXIT=1
~~~

数字：G3 报 1 条；G5 报 6 条（3 个页面、<select>×3 / <input>×2 / <table>×1），退出码 1。

### 3.2 守卫③⑤后绿

~~~
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0
~~~

数字：退出码 0，末行 check_web_style_guards: ok；扫描 27 个 .css（含 6 个新组件 module.css），违规 0；G5 命中 0。

### 3.3 守卫用例（验收命令 6）

~~~
$ rm -f /tmp/t3.xml; cd apps/api && uv run pytest tests/test_web_style_guards.py tests/test_verify_script.py -q --junitxml=/tmp/t3.xml
PIPE_EXIT=0
<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="40" ...>
~~~

数字：40 例（守卫 13 + verify 层图钉 27），0 failed / 0 errors / 0 skipped。单跑守卫：<testsuite ... tests="13" errors="0" failures="0" skipped="0" ...>。守卫用例 ≥12 达标；层图钉法（--list / --dry-run 逐条相等、coverage 顺序）未破。

守卫文件新增/改动的用例（行号见 apps/api/tests/test_web_style_guards.py）：

- test_a_tree_without_a_width_breakpoint_is_reported（G3，第 182 行）
- test_raw_select_input_and_table_in_pages_are_reported（G5，第 201 行）
- test_styled_controls_in_pages_pass（G5，第 229 行）
- test_page_test_files_are_exempt_from_g5（G5，第 251 行）
- test_component_implementations_are_out_of_scope_for_g5（G5，第 262 行）
- write_clean_tokens 夹具补一条宽度断点，使既有 G1/G2/G4 用例仍满足 G3。

### 3.4 前端（验收命令 7）

~~~
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  186 passed (186)

$ pnpm -C apps/web typecheck
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
LINT_EXIT=0
~~~

数字：183 → 186（新增 AppShell 导航高亮 2 例 + Skeleton 开关 1 例），底线只增不减；typecheck / lint 退出码 0。
新增行为单测断言走公开属性/可见行为：导航项 aria-current="page"（非选中项无该属性）；Skeleton 在 loading 时 role="status" 可见、结束后占位消失且 children 可见。

### 3.5 verify --layer all（验收命令 8）

~~~
...
ALL PASS (17 commands) -- evidence: var/evidence/20261012T073033Z-all
VERIFY_ALL_EXIT=0
~~~

从该 evidence 目录抽出的读数：

~~~
TOTAL                                                      6553    305    95%
995 passed, 3 warnings in 81.03s (0:01:21)
 Test Files  26 passed (26)
      Tests  186 passed (186)
All checks passed!
268 files already formatted
openapi.json is up to date
API index is up to date
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
99 passed, 2 warnings in 6.40s
~~~

数字：17 条命令全过、末行 ALL PASS、退出码 0；API 995 passed（含守卫新增 5 例）；coverage floors 过、TOTAL 95%；web 186 passed；contract 的 openapi / api-index / schema.d.ts 零 diff。

### 3.6 变异证明（验收命令 9，取推荐 (a)：删导航项 aria-current）

~~~
sha_before=89e88d20a154670b014c26ced4337cc9a5e19fe34e1df23dccdf9e4e973ca4d1
== 1/3 baseline ==  Test Files 1 passed (1) / Tests 2 passed (2)
== 2/3 mutate ==    mutated 1 occurrence in .../AppShell.tsx
== 2/3 red ==       Test Files 1 failed (1) / Tests 2 failed (2)
                     × marks the nav item of the current route with aria-current
                     × keeps the section highlighted on a nested route
                     Received: aria-current = null
== 3/3 restore ==   Test Files 1 passed (1) / Tests 2 passed (2)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/components/AppShell.tsx)
MUT_EXIT=0
sha_after=89e88d20a154670b014c26ced4337cc9a5e19fe34e1df23dccdf9e4e973ca4d1
CMP_OK
~~~

锚点：AppShell.tsx 的 aria-current={active ? "page" : undefined}。这是真变异（删的是属性本身，不是媒体查询前缀之类的拼写）。--file 用绝对路径；恢复后 sha256 与变异前一致，cmp 逐字节相同。
G3/G5 的守卫本身也先对坏输入红过：G3 用例构造无宽度断点的树、G5 用例构造含裸 <select / <input / <table 的 pages 文件，均断言 returncode != 0 并点名 G3 / G5（见 §3.3）。

### 3.7 改动面自查

~~~
$ git status --porcelain
 M apps/web/src/App.test.tsx
 M apps/web/src/App.tsx
 M apps/web/src/components/Button.module.css
 M apps/web/src/components/Card.module.css
 M apps/web/src/components/Collapsible.module.css
 M apps/web/src/components/Empty.module.css
 M apps/web/src/components/Spinner.module.css
 M apps/web/src/components/Textarea.module.css
 M apps/web/src/components/components.test.tsx
 M apps/web/src/components/index.ts
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/AiSettingsPage.tsx
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/ChatPage.tsx
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewIntroPage.tsx
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewReportPage.tsx
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/InterviewRoomPage.tsx
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/MessageBubble.module.css
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/chat/SessionSidebar.tsx
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/styles/base.css
 M apps/web/src/styles/tokens.css
 M scripts/verify.sh
?? apps/api/tests/test_web_style_guards.py
?? apps/web/src/components/AppShell.module.css
?? apps/web/src/components/AppShell.test.tsx
?? apps/web/src/components/AppShell.tsx
?? apps/web/src/components/Badge.module.css
?? apps/web/src/components/Badge.tsx
?? apps/web/src/components/Input.module.css
?? apps/web/src/components/Input.tsx
?? apps/web/src/components/Select.module.css
?? apps/web/src/components/Select.tsx
?? apps/web/src/components/Skeleton.module.css
?? apps/web/src/components/Skeleton.tsx
?? apps/web/src/components/Table.module.css
?? apps/web/src/components/Table.tsx
?? docs/tickets/p14-web-redesign/T1-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T2-EVIDENCE.md
?? scripts/check_web_style_guards.py

$ git diff --numstat
1	1	apps/web/src/App.test.tsx
13	10	apps/web/src/App.tsx
1	0	apps/web/src/components/Button.module.css
1	0	apps/web/src/components/Card.module.css
5	0	apps/web/src/components/Collapsible.module.css
1	0	apps/web/src/components/Empty.module.css
3	0	apps/web/src/components/Spinner.module.css
1	0	apps/web/src/components/Textarea.module.css
23	1	apps/web/src/components/components.test.tsx
12	0	apps/web/src/components/index.ts
14	27	apps/web/src/pages/AiSettingsPage.module.css
7	9	apps/web/src/pages/AiSettingsPage.tsx
9	1	apps/web/src/pages/ChatPage.module.css
4	22	apps/web/src/pages/ChatPage.tsx
12	6	apps/web/src/pages/InterviewIntroPage.module.css
6	9	apps/web/src/pages/InterviewIntroPage.tsx
12	2	apps/web/src/pages/InterviewReportPage.module.css
1	1	apps/web/src/pages/InterviewReportPage.tsx
10	2	apps/web/src/pages/InterviewRoomPage.module.css
1	1	apps/web/src/pages/InterviewRoomPage.tsx
1	0	apps/web/src/pages/chat/Composer.module.css
10	0	apps/web/src/pages/chat/MessageBubble.module.css
49	6	apps/web/src/pages/chat/SessionSidebar.module.css
30	26	apps/web/src/pages/chat/SessionSidebar.tsx
2	0	apps/web/src/pages/interview/RadarChart.module.css
4	2	apps/web/src/pages/interview/ResumePreviewCard.module.css
5	1	apps/web/src/pages/interview/RoomParts.module.css
2	0	apps/web/src/styles/base.css
33	2	apps/web/src/styles/tokens.css
2	1	scripts/verify.sh
~~~

逐文件说明（T3 新建 / T3 修改 / 前票遗留）：

- T3 新建：apps/web/src/components/AppShell.tsx + AppShell.module.css + AppShell.test.tsx；Select、Input、Table、Badge、Skeleton 各 .tsx + .module.css（共 12 个组件文件）；本文件 docs/tickets/p14-web-redesign/T3-EVIDENCE.md。
- T3 修改：apps/web/src/App.tsx（AppShell 接线）；App.test.tsx（等待空态，见 §五.1 断言调整清单）；components/index.ts（导出新组件）；components/components.test.tsx（Skeleton 用例）；pages 下 AiSettingsPage / ChatPage / InterviewIntroPage / InterviewReportPage / InterviewRoomPage 的 .tsx 与 .module.css（标题行、控件替换、栅格断点、去死代码）；pages/chat/SessionSidebar.tsx + .module.css（二级栏 details 折叠 + 断点）；styles/tokens.css（新增 --br-width-content: 1200px）；scripts/check_web_style_guards.py（守卫脚本覆盖守卫①–⑤）；apps/api/tests/test_web_style_guards.py（追加 G3/G5 用例并补夹具断点）。
- 前票（T1/T2）遗留未提交、T3 未触碰：Button / Card / Collapsible / Empty / Spinner / Textarea 的 .module.css；chat/Composer.module.css、chat/MessageBubble.module.css、interview/RadarChart.module.css、interview/ResumePreviewCard.module.css、interview/RoomParts.module.css；styles/base.css；scripts/verify.sh；T1-EVIDENCE.md、T2-EVIDENCE.md。它们出现在 git status / numstat 里只因 T1/T2 尚未提交。
- 白名单读数：apps/web/src 下 /* allow: */ 共 48 条（T3 新增 5 条组件 / 布局几何，删除 1 条随裸 table 移除）。

## 四、未验证项诚实清单

- 浏览器视觉与两档断点的真实塌缩观感（<1024 单列、二级栏 details 折叠、内容容器 1200 居中）未人工 / 截图核验；AI 无浏览器截图能力。
- hover / active / focus 手感、深色主题下新组件的观感未人工核验；focus 外框沿用 base.css 的全局 :focus-visible。
- MANUAL-TESTING §1.1–1.4 的实时转写 / 答题交互未手测；本票未改 Composer 转写合并语义与 audio 逻辑，也未动 apps/web/src/api、audio、stream。
- bash scripts/compose_smoke.sh 未跑（未改部署面与构建产物；README §4.3 的回归底线之一）。
- Badge / Skeleton 无页面消费点，其实际视觉与消费后的表现未验证；Select / Input / Table 的视觉与 hover 未人工核验。
- 无视觉快照测试（本阶段明确不引）。
- jsdom 不应用媒体查询，断点行为只有静态存在性（G3）与结构/单测保障；真实视口切换未核。
- 未登录态顶栏呈现（保留主导航、隐藏用户区）未获页面批确认。
- 未核 1024px 在真实设备 / 浏览器缩放下的边界取值。

## 五、与提案的偏差（含断言调整清单）

1. **断言调整清单（唯一一条）**：apps/web/src/App.test.tsx 第 23 行由 getByText("还没有消息") 改为 findByText("还没有消息")。原因：页壳把 heading「better-resume」移进顶栏后，findByRole("heading") 在 ChatPage 仍显示「正在检查登录状态…」时就满足，紧随其后的同步 getByText 会在空态渲染前执行。改法是等待同一文本，测试意图（已登录访客看到聊天壳与空态）不变，属票面允许的「文本 / 角色位置」类调整；未删除或削弱任何断言。
2. 写入路径扩到 apps/web/src/App.test.tsx（票面唯一写入路径未列该文件）。除此之外未扩路径：scripts/verify.sh 零改动；apps/web/src/api、audio、stream 与 openapi.json / schema.d.ts 零改动。
3. 断点实现取「窄屏单列为默认、@media (min-width: 1024px) 恢复双栏」的写法（票面表述为 ≥1024 照旧）；媒体查询值仍是 1024px，并满足验收项「加 ≥1 条 (min-width: 1024px) 档断点」。
4. 二级栏「顶部折叠」用原生 <details> / <summary>（窄屏默认收起），未引入 JS 开关与对应行为单测；票面行为单测只点名导航高亮与 Skeleton，本项没有指定测试缝。
5. 页内标题由 h1 降为 h2（顶栏品牌成为唯一 h1）。既有页面测试未断言这些标题，断言零改动；此为角色位置调整。
6. 删除 InterviewIntroPage.module.css 的 .back 与 AiSettingsPage.module.css 的 .table 规则：返回对话链接与裸 table 一并消失，规则失去消费点，避免死代码。
7. Badge 未消费 --br-gradient-badge，五档 tone 全走语义色 token；渐变 token 的消费留给 T4–T8（T2 已登记为预留槽位）。
8. 新增 3 例行为单测（AppShell 导航高亮 2 + Skeleton 1）超出票面最小集（导航高亮，Skeleton 仅在带逻辑时测）；未改数据层断言、未删测试。
9. styles/tokens.css 新增 --br-width-content: 1200px（写入路径 #4 允许的内容容器宽度 token 最小新增）；为非主题依赖，无需 prefers-color-scheme: dark 重述，G1/G1b 通过。
10. SessionSidebar.tsx 内联 class 拼接由模板字符串改为数组 join、aria-label 由模板字符串改为字符串拼接（等价），以避免外层工具链对模板字符串的处理差异；渲染结果与可访问名不变。
