# P14-T5 验收包 — 上传页（dropzone 主视觉 + 侧重 Select + 继续列表卡片化）

- 票据：docs/tickets/p14-web-redesign/T5-upload-page.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.4 上传页线框 / §1.5 / §4.1；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

按已确认的 §1.4 上传页线框重排，不动业务：

1. 主区 7fr:5fr（上传优先）：窄屏单列，≥1024 左 7fr 上传、右 5fr 预览与继续列表。
2. dropzone 放大为主视觉：渐变圆形图标 + 拖拽/点击文案 + 支持格式说明；拖拽与点击走同一条既有校验路径。
3. 面试侧重用样式化 Select，每个选项带一行说明；枚举值与「选择值写入受控状态」的语义不变。
4. 进度条带百分比与阶段文案，宽度仍由既有 upload.progress 驱动。
5. 「继续上次面试」改卡片行：类型 + 题数 + 时间 + 状态徽章 + 继续按钮。
6. 空态用插画感 Empty（组件不变，插画走 action 槽位）。

不做：上传/出题的请求语义与降级文案、数据流、REST 契约、路由表、依赖、src/api、src/audio、src/stream、components/、styles/、守卫脚本与守卫测试、既有测试断言；无 commit。

## 二、实现决定交代

### 2.1 版式（线框：主区 7fr:5fr，上传优先）

- `.grid` 窄屏 `minmax(0, 1fr)`，`@media (min-width: 1024px)` 改 `minmax(0, 7fr) minmax(0, 5fr)`；沿用全站唯一断点档 1024px（T3 约定）。
- 上传卡改 `raised`（白底 + 柔和阴影）承担主视觉；侧列两张卡保持默认 surface，形成层级。
- 页内保留标题行（h2「模拟面试」+ 一行说明），顶栏由 AppShell 提供。

### 2.2 dropzone 主视觉（线框：图标 + 拖拽文案 + 支持格式）

- 图标：40px 圆形底（`--br-space-7`）+ `--br-gradient-hero`，线性箭头图标用 `--br-color-accent-contrast`；这是 T2 登记给「T5 上传页主视觉」的预留渐变槽位落点。
- 文案：已选文件时显示文件名，否则「拖拽 PDF 到此处，或点击选择」；下方一行支持格式（带文本层 PDF、上限 10MB、扫描件先 OCR）。
- 拖拽：`<label>` 上 `onDragOver` 阻止默认，`onDrop` 把 `event.dataTransfer.files[0]` 交给既有 `upload.selectFile`，与点击选择同一条校验与状态路径；未接新的上传逻辑。
- 几何：最小高度 220px（该行 allow 理由随值重写，白名单条数不变）；虚线边框等既有 allow 原样保留。

### 2.3 侧重 Select 的逐项说明（线框：每项带一行说明）

- 值仍是 `INTERVIEW_TYPE_OPTIONS` 的四个枚举值（auto / fundamentals / project / internship），未增删改；`onChange` 仍写 `setInterviewType(event.target.value)`。
- 原生 `<select>` 的 `<option>` 只能渲染一行，逐项说明接在 option 文本同一行：`{label} · {说明}`。说明表 `INTERVIEW_TYPE_NOTES` 定义在页面内，不改 `interviewTypes.ts`、不动 `interviewTypeLabel` 的短标签语义（继续列表仍显示短标签）。

### 2.4 进度条（线框：百分比 + 阶段文案）

- `percent = Math.round(upload.progress * 100)`；阶段文案读 `upload.stage`（generating → 「正在生成题目…」，否则「正在上传简历…」）。
- 轨道带 `role="progressbar"` / `aria-label="上传进度"` / `aria-valuenow`；`.bar` 的 `width` 仍由 percent 驱动，行为等价，只是把单轨拆成「文案行 + 轨道」。
- 高度/圆角仍走 token；6px 轨道高度沿用既有 allow。

### 2.5 「继续上次面试」卡片行（线框：时间 / 状态徽章 / hover 进入）

- 行内：类型名 + 「N 题 · 时间」+ 状态徽章（`ready` → accent「待开始」；`in_progress` → success「进行中」）+「继续」按钮；进入动作仍走 `restoreInterview` + 跳转。
- 整行不设为按钮：进入动作由行内「继续」按钮承担，保留既有可访问名与既有断言（`getByRole('button', { name: '继续' })`），避免嵌套交互元素。
- 行 hover：`--br-color-accent-muted` 弱背景 + `--br-shadow-sm`（沿用 T10 对上传页行的 hover 口径）。
- 时间取接口串前 16 位（YYYY-MM-DD HH:mm），不做时区换算，展示稳定且不依赖运行环境时区。

### 2.6 空态（线框：插画感 Empty）

- 仍用 Empty 组件，未改组件；插画感来自 `action` 槽位：40px 圆形底（`--br-color-accent-muted`）+ 线性文档图标（`--br-color-accent`）。

### 2.7 ResumePreviewCard（侧列 5fr）

- 仅样式：两项统计改 raised 小瓦片（surface-raised + radius-md + padding），降级提示补 radius-md。
- 降级路径的 TSX 零 diff：`role="alert"` 与 `degradedNotice(...)` 的文案一字未动（P13 语义，见 §3.4）。

### 2.8 守卫与动效

- 白名单：本票新增 0 条（dropzone 最小高度 96px allow 改为 220px allow，同文件条数不变）；本票两个文件实测 7 条 allow（页 5 + 卡 2）。
- 动效：`.dropzone` 与 `.sessionRow` 各一条 transition（`--br-duration-fast`），都在同文件 `@media (prefers-reduced-motion: reduce)` 内被同选择器重访；`.bar` 既有覆盖保留。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行，前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
~~~

### 3.1 守卫①–⑤

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0
~~~

数字：退出码 0；末行 ok；扫描 27 个 .css；违规 0。

### 3.2 红-绿（先红后绿）

实现前，同一测试文件：

~~~text
 Test Files  1 failed (1)
      Tests  3 failed | 9 passed (12)
VITEST_EXIT=1
~~~

三条新用例全红：option 无逐项说明、页面无 progressbar、dropzone 不接拖拽。实现后见 §3.3。

### 3.3 行为单测与全量

~~~text
$ pnpm -C apps/web test --run src/pages/InterviewIntroPage.test.tsx
 Test Files  1 passed (1)
      Tests  12 passed (12)
VITEST_EXIT=0

$ pnpm -C apps/web typecheck
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
LINT_EXIT=0

$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  197 passed (197)
VITEST_EXIT=0
~~~

数字：本票文件 12 例全绿（原 9 + 新 3）；typecheck / lint 退出码 0。
全量套件实测 26 文件 / 197 例全绿（实现前基线 187 例；本波 T4/T6/T8 与本票的新增用例合计只增不减）。本票写入路径之外的文件在并行执行期间有短暂红，收口时为全绿。

本票行为单测清单（`apps/web/src/pages/InterviewIntroPage.test.tsx`）：

| 切片 | 用例 | 断言 |
| --- | --- | --- |
| 1 | keeps the chosen focus in controlled state and explains each option | change 后 select 值 = project；「项目深挖」选项文本含逐项说明 |
| 2 | drives the progress bar and its percentage from the upload progress | onProgress(0.42) 后 progressbar aria-valuenow=42、.bar width=42%、阶段文案在 |
| 上传（线框新增） | accepts a dropped pdf through the same validation path | label 上 drop 一个 PDF 后「开始面试」可点（与点击同路径） |

### 3.4 降级文案不退化（切片 3）

~~~text
$ git diff --numstat -- apps/web/src/pages/interview/ResumePreviewCard.tsx
（无输出：TSX 零 diff）

$ pnpm -C apps/web test --run src/pages/interview/ResumePreviewCard.test.tsx
 Test Files  1 passed (1)
      Tests  3 passed (3)
VITEST_EXIT=0
~~~

数字：降级渲染的 TSX 零 diff；既有「says out loud when the generation degraded」用例（断言 `role="alert"` 内含「没有匹配到八股语料」）保持绿；「简历没有解析出可用的文本层…」映射在 `interview/degraded.ts`，本票未触碰。手测第 10/11 项（MANUAL-TESTING §1.5）的文案因此在代码面上原样保留。

### 3.5 变异证明

~~~text
sha_before=3fb9294b1bf8a0d10b1a348d238bb3aa75a93cfa090a985d38f907b388dee65d
== 1/3 baseline ==  12 passed (12)
== 2/3 mutate ==    mutated 1 occurrence in /root/better resume/apps/web/src/pages/InterviewIntroPage.tsx
== 2/3 red ==       2 failed | 10 passed (12)
                    × keeps the chosen focus in controlled state and explains each option
                    × sends the chosen interview focus when creating the session
                      expected: { interview_type: "project" } / received: { interview_type: "auto" }
== 3/3 restore ==   12 passed (12)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/InterviewIntroPage.tsx)
MUT_EXIT=0
sha_after=3fb9294b1bf8a0d10b1a348d238bb3aa75a93cfa090a985d38f907b388dee65d
CMP_OK
~~~

命令（--file 用绝对路径）：

~~~bash
bash scripts/verify_mutation.sh --test 'pnpm -C apps/web test --run src/pages/InterviewIntroPage.test.tsx' \
    --file '/root/better resume/apps/web/src/pages/InterviewIntroPage.tsx' \
    --find 'setInterviewType(event.target.value);' \
    --replace 'setInterviewType("auto");'
~~~

数字：锚点是受控状态写入本身（真变异，不是拼写或媒体查询前缀）；基线绿 → 变异红（2 例点名）→ 恢复绿；恢复后 sha256 与变异前一致，cmp 逐字节相同；--file 绝对路径。

### 3.6 改动面自查

~~~text
$ git status --porcelain
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/AiSettingsPage.test.tsx
 M apps/web/src/pages/AiSettingsPage.tsx
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewIntroPage.test.tsx
 M apps/web/src/pages/InterviewIntroPage.tsx
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewReportPage.test.tsx
 M apps/web/src/pages/InterviewReportPage.tsx
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/InterviewRoomPage.test.tsx
 M apps/web/src/pages/InterviewRoomPage.tsx
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/pages/interview/RoomParts.tsx
?? docs/tickets/p14-web-redesign/T5-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md
~~~

~~~text
$ git diff --numstat
12	8	apps/web/src/pages/AiSettingsPage.module.css
28	0	apps/web/src/pages/AiSettingsPage.test.tsx
38	25	apps/web/src/pages/AiSettingsPage.tsx
130	14	apps/web/src/pages/InterviewIntroPage.module.css
60	2	apps/web/src/pages/InterviewIntroPage.test.tsx
120	29	apps/web/src/pages/InterviewIntroPage.tsx
171	42	apps/web/src/pages/InterviewReportPage.module.css
108	0	apps/web/src/pages/InterviewReportPage.test.tsx
164	66	apps/web/src/pages/InterviewReportPage.tsx
69	13	apps/web/src/pages/InterviewRoomPage.module.css
81	6	apps/web/src/pages/InterviewRoomPage.test.tsx
61	23	apps/web/src/pages/InterviewRoomPage.tsx
25	0	apps/web/src/pages/interview/RadarChart.module.css
9	1	apps/web/src/pages/interview/ResumePreviewCard.module.css
128	19	apps/web/src/pages/interview/RoomParts.module.css
70	21	apps/web/src/pages/interview/RoomParts.tsx
~~~

逐文件说明：

- 本票写入（4 文件，全在工作区，未 commit）：
  - `apps/web/src/pages/InterviewIntroPage.tsx`（+120 −29）：7fr:5fr 栅格、dropzone 主视觉与拖拽接线、Select 逐项说明、进度条百分比与阶段文案、继续列表卡片行、空态插画槽位；请求语义与导航逻辑原样。
  - `apps/web/src/pages/InterviewIntroPage.module.css`（+130 −14）：上述版式与状态的样式；删去失去消费点的 `.hint`，`.progress` 拆为文案行与 `.track`。
  - `apps/web/src/pages/InterviewIntroPage.test.tsx`（+60 −2）：新增 3 条行为单测（切片 1 / 2 / 拖拽）；原有 9 条用例断言未改。
  - `apps/web/src/pages/interview/ResumePreviewCard.module.css`（+9 −1）：统计瓦片与降级提示圆角两处样式。
- 同工作区并行票的在飞文件（非本票写入，读数随其进度变化）：`InterviewReportPage.*`、`interview/RadarChart.module.css`（T4）；`InterviewRoomPage.*`、`interview/RoomParts.*`（T6）；`AiSettingsPage.*`（T8）；未跟踪的 `T8-EVIDENCE.md`（T8）与本文件。
- 本票未触碰：`apps/web/src/components/`、`apps/web/src/styles/`、`src/api`、`src/audio`、`src/stream`、`scripts/check_web_style_guards.py`、`apps/api/tests/test_web_style_guards.py`、`scripts/verify.sh`、README、T1–T10 票面与既有 EVIDENCE、路由表、依赖清单。

## 四、未验证项诚实清单

- 浏览器视觉观感（渐变图标、raised 卡、7fr:5fr 比例、卡片行密度、空态插画位）AI 无浏览器与截图能力，未核；截图按 README 口径由 T9 统一收口。
- 深色主题下渐变图标、raised 瓦片与 accent-muted hover 的观感未人工核对（只保证引用 token 在深色块有定义）。
- 拖拽上传只在 jsdom 用 `fireEvent.drop` 覆盖页面接线；真实浏览器的拖拽文件、拖拽悬停态（未做 dragenter 高亮）未核。
- hover / active / focus 手感未人工核验。
- 「继续上次面试」行的时间格式（YYYY-MM-DD HH:mm、不做时区换算）未获页面批确认，也未单独断言；`formatSessionTime` 未被单测覆盖（票面未点名该缝）。
- 未跑 bash scripts/verify.sh --layer all 与 apps/api 的 pytest（并发安全约定：波次收口由主代理统一跑）。
- 未跑 bash scripts/compose_smoke.sh（未改部署面与构建产物，缓存头与 bundle hash 未核）。
- 无视觉快照测试（本阶段明确不引）；jsdom 不应用媒体查询与伪类。

## 五、与提案的偏差

1. 「每项带一行说明」落地为 option 单行文本内追加说明（原生 select 无法渲染两行 option）；未新增自定义下拉组件（票面限既有样式化组件）。说明表在本票新增于页面文件内，未改 `interviewTypes.ts`。
2. 「hover 进入」：整行未设为按钮，进入动作由行内「继续」按钮承担，以保留既有可访问名与既有断言；行的 hover 弱背景 + 阴影由 T10 口径延伸。
3. 新增拖拽行为与一条行为单测（票面切片只点名 3 条缝）：线框要求 dropzone 出现「拖拽文案」，若只有文案没有 drop 接线，文案失真；实现复用既有 `selectFile`，未改任何上传语义。
4. 上传卡 `raised`、ResumePreviewCard 统计改瓦片、空态插画走 Empty 的 `action` 槽位：均为线框未写处的保守做法，登记待确认。
5. 时间展示不做时区换算；如要本地时区展示，需要产品口径。
6. 本票写入路径之外的并行票文件不属于本票改动面，见 §3.6；本票文件与全量套件的收口读数均为绿（§3.3）。
