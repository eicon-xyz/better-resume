# P14-T4 验收包 — 报告页（hero + 雷达生长动画 + 按类卡片 + 逐题折叠）

- 票据：docs/tickets/p14-web-redesign/T4-report-page.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.4 报告页线框 / §1.5 视觉语言；T2-EVIDENCE §2.2 渐变槽位；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

本票只重排报告页版式与呈现，不动业务语义：

1. **hero 区**：综合分大数字（消费 --br-text-hero 与 --br-gradient-score）+ 雷达图并排（面积由中心展开的生长动画；prefers-reduced-motion 下直接呈现）+ 四维小分条；hero 自身用 --br-gradient-hero 做点缀。
2. **第二行**：按类给分卡片栅格（类别徽章消费 --br-gradient-badge / 分数或「样本不足」/ 题数 / 评语）；改进建议卡带序号与强调样式。
3. **第三行**：逐题回放改折叠分组（按主问题 topic_no 分组、追问缩进、默认展开第一题、含全部展开/收起）。
4. 行为单测只写在票面点名的缝上（折叠分组开合、全部展开/收起、无分数类别的「样本不足」语义）；纯样式不写测试；雷达几何与 11 例既有测试零改动。

不做：不改业务逻辑、数据流、TanStack Query/zustand 用法、REST 契约、路由表；不碰 src/api、src/audio、src/stream、apps/web/src/components、apps/web/src/styles、守卫脚本与守卫测试、verify.sh、README、T1–T10 票与既有 EVIDENCE；不新增依赖、不引 webfont/动效库；不 commit。

## 二、实现决定交代

### 2.1 版式与线框映射

- **hero** 用既有 Card（raised）承载：卡内顶部一条 --br-gradient-hero 渐变徽条（宽 --br-space-7=40、高 --br-space-1=4、圆角 pill）作点缀，不铺大面；卡内 .heroMain 在 ≥1024 为两列（综合分块 | 雷达图），窄屏单列；四维小分条在 hero 卡内下方，≥1024 两列。
- **综合分大数字**：字号 --br-text-hero（T10 已落位），配色走 --br-gradient-score（background-clip: text），aria-label=综合得分 与既有测试口径不变。
- **第二行按类给分**：每类一张 Card，头行 = 类别徽章（--br-gradient-badge 底 + --br-color-accent 字）+ 分数位；随后题数与评语。栅格窄屏单列、≥1024 三列。
- **改进建议**保留在 hero 之后：summary + 带序号 chip 的建议列表（序号底用 --br-color-accent-muted，非渐变，保证渐变只留 hero / 综合分 / 类别徽章三处）+ 反复缺失。
- **第三行逐题回放**：按 topic_no 分组（同组按出现顺序）；组头文案「第 N 题 · 主问题」；组内主问题卡 + 追问卡（缩进 --br-space-5）。默认只展开第一组。组数 > 1 时，标题行右侧显示「全部展开 / 全部收起」切换按钮。

### 2.2 交互与状态

- 开合状态为 openKeys: string[] | null；null 表示「用户尚未手动开合」，此时生效集合 = [第一组 key]；任意一次手动开合后转为显式集合。点组头、全部展开、全部收起走同一状态。
- 折叠容器复用既有 Collapsible（button + aria-expanded + chevron 过渡），未新造控件；页内无裸 select/input/table（守卫⑤）。
- 既有交互未动：再面一次 / 回到对话 / 回到面试入口三个按钮与空态、加载态语义保持。

### 2.3 雷达生长动画

- 在既有类 .area（面积 polygon）与 .dot（数据点 circle）上挂动画：transform-box: view-box + transform-origin: center（origin 即 viewBox 中心，等于 buildRadar 默认 center=110，所以面积与点由中心展开），@keyframes radarGrow 从 scale(0) 到 scale(1)，时长 --br-duration-normal（200ms）ease-out both。
- reduced-motion 分支：同文件 @media (prefers-reduced-motion: reduce) 内以同选择器 .area, .dot 重访并 animation: none，直接呈现终态（守卫④机器兜底见 §3.3 的第二个变异证明）。
- 雷达几何 apps/web/src/interview/radar.ts 与 radar.test.ts 的 11 例一行未动；RadarChart.tsx 未改（动画只挂在既有类上）；颜色仍全部走 token。

### 2.4 P11 语义与四维小分条的文案顺序

- 「样本不足」判定与文案不改：THIN_SAMPLE = 样本不足；score 为 null/undefined 时显示徽章文案而非数字；评语等于 THIN_SAMPLE 时不再重复显示；有分数时分数位仍带「<类别>得分」的 aria-label。
- 无分数类别改由既有 Badge（tone=neutral）承载「样本不足」；该分支不再有「得分」aria-label——那个标签只属于数字位，避免把「样本不足」读成得分。
- 四维小分条每行文案为「分值 + 维度名」（如「80 准确性」）再跟一条进度条：既有报告页测试用 getByText(/^维度名/) 断言雷达轴标签唯一出现，分值前置使该断言继续成立，既有断言一字未改。

### 2.5 动效与 token 边界

- 本票只新增 1 处 animation（RadarChart.module.css 的 .area, .dot）并配 1 条同选择器 reduced-motion 重访；四维小分条是静态呈现，不设过渡，不新增 G4 面。
- 渐变只消费 T2 的三个槽位：--br-gradient-hero（hero 徽条）、--br-gradient-score（综合分）、--br-gradient-badge（类别徽章），无第四处。
- 未新增 token；未新增 allow。InterviewReportPage.module.css 的 allow 由 3 条减为 1 条（删掉旧布局的 48px 名称列 / 72px 分数列两条几何放行，沿用逐题回放卡 1px 边框一条）；RadarChart.module.css 的 2 条 allow 原样保留。

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

$ grep -rn 'allow:' apps/web/src | wc -l
43
~~~

数字：退出码 0；扫描 27 个 .css；违规 0 条；末行 check_web_style_guards: ok。全站 allow 实测 43 条（工作区与并行票共享，该总数含其他票的增减）；本票自己的读写文件里只有 InterviewReportPage.module.css:233 一条（逐题回放卡 1px 边框），RadarChart.module.css:7 与 :35 两条为既有，未动。

### 3.2 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  197 passed (197)
EXIT=0

$ pnpm -C apps/web exec vitest run src/pages/InterviewReportPage.test.tsx
 ✓ src/pages/InterviewReportPage.test.tsx (11 tests)
 Test Files  1 passed (1)
      Tests  11 passed (11)

$ pnpm -C apps/web typecheck
$ tsc --noEmit
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：全量 26 文件 / 197 例全绿（本票开工基线为 186 例；本票在 InterviewReportPage.test.tsx 由 7 例增到 11 例，净增 4 例；其余增量来自并行票在同一工作区的写入）。typecheck 与 lint 退出码 0。

### 3.3 变异证明（两处，均「基线绿 → 变异红 → 恢复绿」）

**（1）折叠分组默认展开第一组**（本票行为单测，票面要求的 ×1）：锚点取实现里算默认开合集合的表达式，删掉「默认展开第一组」后即成真变异。

~~~text
$ sha_before=$(sha256sum apps/web/src/pages/InterviewReportPage.tsx | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh \
    --test 'pnpm -C apps/web exec vitest run src/pages/InterviewReportPage.test.tsx' \
    --file '/root/better resume/apps/web/src/pages/InterviewReportPage.tsx' \
    --find 'openKeys ?? (firstGroup ? [firstGroup.key] : [])' --replace 'openKeys ?? []'
== 1/3 baseline: the test must PASS on the untouched implementation ==
 Test Files  1 passed (1)
      Tests  11 passed (11)
== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/pages/InterviewReportPage.tsx ==
mutated 1 occurrence in /root/better resume/apps/web/src/pages/InterviewReportPage.tsx
== 2/3 red: the test must FAIL on the mutated implementation ==
 × replays every turn including the follow-up
 × opens only the first question group by default
 × toggles one question group from its header
 Test Files  1 failed (1)
      Tests  3 failed | 8 passed (11)
ok: mutation was caught
== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/pages/InterviewReportPage.tsx sha256=52859a928c35d268…
      Tests  11 passed (11)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/InterviewReportPage.tsx)
MUT1_EXIT=0
sha_before=52859a928c35d2687b85c98178ba978382ce08c1344ebf086ee30fc0dcab5047
sha_after=52859a928c35d2687b85c98178ba978382ce08c1344ebf086ee30fc0dcab5047
CMP1_OK
~~~

数字：基线 11/11 绿 → 变异后 3 例红（含本票两条折叠用例）→ 恢复 11/11 绿；恢复后 sha256 与变异前同为 52859a928c35d268…，cmp 逐字节相同；--file 用绝对路径。

**（2）雷达生长动画的 reduced-motion 分支**（票面切片 2 的守卫④机器兜底）：锚点取 reduced-motion 块里的 animation: none;——删掉它就让动画失去 reduce 重访。

~~~text
$ sha_before=$(sha256sum apps/web/src/pages/interview/RadarChart.module.css | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh \
    --test 'python3 scripts/check_web_style_guards.py' \
    --file '/root/better resume/apps/web/src/pages/interview/RadarChart.module.css' \
    --find '    animation: none;' --replace ''
== 1/3 baseline: the test must PASS on the untouched implementation ==
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
== 2/3 red: the test must FAIL on the mutated implementation ==
pages/interview/RadarChart.module.css:41: G4 .area,
.dot 的动画没有 prefers-reduced-motion 处理（守卫④）
check_web_style_guards: 1 violation(s)
ok: mutation was caught
== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/pages/interview/RadarChart.module.css sha256=97462ab1b292a9c7…
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/interview/RadarChart.module.css)
MUT2_EXIT=0
sha_before=97462ab1b292a9c7ef39961122868faa9fac155af5fcd7b21fb25cc88f030828
sha_after=97462ab1b292a9c7ef39961122868faa9fac155af5fcd7b21fb25cc88f030828
CMP2_OK
~~~

数字：基线绿 → 变异红（G4 点名 pages/interview/RadarChart.module.css:41）→ 恢复绿；恢复后 sha256 与变异前同为 97462ab1b292a9c7…，cmp 逐字节相同。

### 3.4 行为单测清单（InterviewReportPage.test.tsx，新增 4 例；既有 7 例断言未改）

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | opens only the first question group by default | 第一组 aria-expanded=true 且内容可见；第二组 aria-expanded=false 且内容不在 DOM |
| 2 | toggles one question group from its header | 点组头 true→false（内容消失），再点 false→true（内容回来） |
| 3 | expands and collapses every question group at once | 点「全部展开」两组都展开且第二组内容可见、按钮变「全部收起」；点「全部收起」两组都收起 |
| 4 | shows a thin-sample badge instead of a score for a category without one | 有分数类别有「项目得分」数字位 78.3；无分数类别没有「八股得分」数字位，改为显示「样本不足」徽章文案 |

数字：本票新增 4 例行为单测；本次未对面板式/雷达几何写样式测试（README §4.1：纯样式不写测试），雷达侧由守卫④与 §3.3 的第二个变异证明兜底。

### 3.5 改动面自查

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
?? docs/tickets/p14-web-redesign/T4-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T5-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md

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

逐文件说明（本票写入范围内 4 个文件 + 1 个新建验收包）：

- apps/web/src/pages/InterviewReportPage.tsx（+164 −66）：按线框重排——hero（渐变徽条 + 综合分 + 雷达 + 四维小分条）、改进建议（带序号）、按类卡片栅格、逐题折叠分组；新增 groupTurns / TurnCard / openKeys 状态。业务逻辑与查询调用不变（仍 buildReportViewModel + useInterviewReport）。
- apps/web/src/pages/InterviewReportPage.module.css（+171 −42）：hero / 四维小分条 / 类别栅格 / 折叠分组 / 序号 chip 的版式与状态；删去旧两列 .grid 与按类平铺 ul 的列宽放行。
- apps/web/src/pages/InterviewReportPage.test.tsx（+108 −0）：只追加 4 例新用例与 GROUPED 夹具，未改既有 7 例的断言。
- apps/web/src/pages/interview/RadarChart.module.css（+25 −0）：面积与数据点的生长动画 + reduced-motion 重访；无删改。
- docs/tickets/p14-web-redesign/T4-EVIDENCE.md（本文件，新建）。

未触碰：apps/web/src/interview/radar.ts 与 radar.test.ts（git diff 为空）、RadarChart.tsx（未改）、apps/web/src/components/**、apps/web/src/styles/**、scripts/check_web_style_guards.py、apps/api/tests/test_web_style_guards.py、scripts/verify.sh、src/api、src/audio、src/stream、README、T1–T3/T10 票与 EVIDENCE；无新依赖；无 commit。

说明：工作区同时承载并行票（T5/T7/T8 等）的写入，故 git status / numstat 原文里出现本票范围外的文件；本票只写了上面 4 个文件。

## 四、未验证项诚实清单

- 浏览器视觉观感与手感全部未验证：hero 两列比例、四维小分条的高度与对比、类别卡片三列的疏密、追问缩进的层次、折叠组头的可点性、综合分渐变文字的清晰度（background-clip: text）。本票无浏览器与截图能力；截图按 README 当前口径由 T9 统一收口，本票不拍。
- 雷达生长动画的实际观感（面积与数据点由中心展开的节奏、text 轴标签不随之缩放是否协调）未在真浏览器确认；jsdom 不应用媒体查询与动画，只有静态声明与守卫④/变异证明。
- prefers-reduced-motion 真机开启后的「直接呈现」未人工核对；本票只保证声明被 reduce 重访（守卫④静态校验 + §3.3 第二个变异证明）。
- 深浅两套主题下的渐变观感（尤其 --br-gradient-score 的渐变文字在深色块 #818cf8→#a5b4fc 上的可读性、--br-gradient-badge 深色底配 --br-color-accent 字的对比度）未人工核对；只保证引用的 token 深浅双定义存在（守卫①）。
- 「分值 + 维度名」的文案顺序（如「80 准确性」）是按现有测试对雷达轴标签唯一性的约束选定的；用户是否接受该顺序未确认，见 §五。
- --br-gradient-hero 仅作 40×4 徽条点缀，是否达到「hero 渐变」的预期强度属主观判断，未验证。
- 报告页在窄屏（<1024）单列塌缩后的实际排版未核；断点为静态声明。
- 未跑 bash scripts/verify.sh --layer all 与 apps/api 的 pytest/uv 命令（本轮 4 张票并行，波次收口由主代理统一跑）；未跑 compose_smoke.sh。
- 未做 MANUAL-TESTING 的人工项（hover/active 手测渲染半边）；本票未涉及转写/答题交互。

## 五、与提案的偏差

1. 报告页第二行「按类给分」用既有 Card 组件承载每类卡片（而非页面自定义卡片容器），以复用卡片的 1px 发丝边框与圆角，同时不新增 allow。
2. 四维小分条每行文案取「分值 + 维度名」（分值在前），而非「维度名 + 分值」：既有测试以 getByText(/^维度名/) 断言雷达轴标签唯一出现，分值前置可让雷达与小分条同时保留各自的维度文字而该断言继续通过（既有断言一字未改）。若用户更接受「维度名 + 分值」，需要同步调整那条既有断言的作用域，超出本票「不改既有测试断言」的红线，故停下来报。
3. 无分数类别改用既有 Badge 组件（tone=neutral）承载「样本不足」，因此该分支不再有「<类别>得分」的 aria-label；判定与文案语义未变（P11）。有分数类别的数字位 aria-label 原样保留。
4. hero 未铺渐变底，--br-gradient-hero 只落在卡顶部一条 40×4 徽条上，取 README §1.5「渐变只做点缀，不铺大面」。
5. 「全部展开/收起」在只有 1 个分组时不渲染（单组时该开关无意义）；该渲染条件由线框未写明处按保守做法选定。
6. 本票未改 RadarChart.tsx（生长动画只挂在既有 .area / .dot 类上），几何与 11 例测试零改动。