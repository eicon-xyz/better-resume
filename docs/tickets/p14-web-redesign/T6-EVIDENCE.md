# P14-T6 验收包 — 面试间（房间二级行 + 问题卡升级 + composer 卡片化）

- 票面：docs/tickets/p14-web-redesign/T6-interview-room.md
- 线框依据：README §1.4「面试间」、§1.5 视觉语言（逐块已获用户确认）
- 基线：HEAD=1047bd1（工作区干净开工），改动全留工作区，未 commit
- 唯一写入路径：InterviewRoomPage.tsx / .module.css / .test.tsx、pages/interview/RoomParts.tsx / .module.css、本文件

## 一、意图复述

在不改业务逻辑、数据流、TanStack Query / zustand 用法、REST 契约与路由表的前提下，把面试间按线框重排为视觉层：

1. **房间二级行**（页壳顶栏之下）：进度步骤条「题 2/5」+ 类别徽章 + 结束按钮。
2. **问题卡**：题面走大字号（--br-text-xl）、focus_points 由顿号串改为标签、类别徽章用 --br-gradient-badge 渐变点缀。
3. **反馈区**：按时间序成组、最新一条高亮。
4. **composer**：卡片化（字数计数、语音按钮录音态、快捷键提示、吸底）。
5. **<1024**：上下堆叠、反馈折叠、composer 吸底（沿用既有 1024px 断点档）。

红线：转写合并语义（三层）与 audio / api / stream 零改动；composer 的提交与禁用语义只由既有状态驱动；结束按钮行为不变。

## 二、实现决定交代

### 2.1 房间二级行与进度步骤条

- 二级行是页内 header（.roomBar）：ProgressBar + CategoryBadge + 结束按钮（右侧 group，margin-left:auto）。页内原「模拟面试」h2 去掉：页壳顶栏已是唯一品牌，线框的该行只列步骤条 / 徽章 / 结束按钮。
- 标签文案按线框取「题 X / Y」：X = min(answered + 1, total)、Y = total（无题时 0 / 0）。steps 条一题一格，格子状态只由 answered / total 推导（done / current / todo），是装饰层（aria-hidden），文本信息全在标签里。
- 结束按钮保持原 onClick 与 loading 语义，仅换到二级行右端。

### 2.2 类别徽章的来源

- 取 state.currentQuestion.category（GeneratedQuestionView 的既有字段），映射 fundamentals/project/internship → 八股/项目/实习；陌生取值原样显示，缺失则不渲染（不替后端猜类别）。
- roomStore 的 InterviewTurn 不带 category，本次没有改数据层：QuestionCard 新增可选 category prop，由页面把 state.currentQuestion.category 传下去。
- 二级行与问题卡共用 RoomParts 的 CategoryBadge，避免两处渐变样式各写一份。

### 2.3 问题卡

- 题面 .questionText 由 --br-text-lg 提到 --br-text-xl（26px），行高 --br-leading-tight。
- focus_points 改为 Badge 组件标签行：ul[aria-label="考察要点"] + 每点一个 Badge，保留「考察要点」可见文字标签。
- 类别徽章背景走 --br-gradient-badge（§1.5 允许的三处渐变点缀之一），圆角沿用 T10 的 --br-radius-xs。

### 2.4 反馈分组与最新高亮

- 后端 turn 不带 per-turn 时间戳（session 只有 created_at / updated_at），房间内也无法取到时间：**「按时间分组」落为单一时间序分组** —— 一个有序列表 ol[aria-label="反馈时间线"]，条目顺序就是既有数组顺序（提交先后），不伪造时间戳、不做二次排序。
- 最新一条 = 既有数组末位（latestTurnIndex = answeredTurns.length - 1），该 li 带 data-latest="true" 与可见「最新」标签；高亮 CSS 只认 [data-latest="true"]（描边转 accent + --br-shadow-md），保证 DOM 标记与视觉同源。

### 2.5 窄屏反馈折叠（<1024）

- 折叠开关是已有的 Button（ghost / sm）+ aria-expanded，由 feedbackOpen 这一处 UI state 控制；不开 matchMedia、不新增状态源。
- .feedbackBody 默认 display:none，[data-open="true"] 展开；@media (min-width: 1024px) 块里 .feedbackBody 常显、.feedbackToggle 隐掉 —— 即窄屏默认折叠、宽屏与改版前一样直接看到反馈。
- 未用 Collapsible：它把开关与内容放在同一根节点，无法只在 ≥1024 隐掉开关；也未用 <details>，避免闭包内容在宽屏不能强制展开的不确定性。

### 2.6 composer 卡片化

- 卡片：sticky bottom:0 + margin 让出四周 + 1px token 描边 + --br-radius-lg + --br-shadow-sticky（吸底专用的既有阴影 token）+ focus-within 转 accent；transition 全部在 prefers-reduced-motion 下被同选择器重访。
- 字数：value.trim().length（与实际提交的文本同一口径），渲染为「N 字」；不含任何新状态。
- 提交 / 禁用：仍是 disabled || submitting 与「空文本不提交」的原有语义，零改动。
- 语音按钮：recording 时切 secondary + aria-pressed=true + data-recording="true" + 引点（--br-color-danger，animation 在 reduced-motion 下 animation:none）；可访问名仍是「语音输入」/「停止录音」。
- 快捷键提示：常显「Ctrl / ⌘ + Enter 提交」，placeholder 里重复的括号提示随之移除。

### 2.7 断点

- .body 默认单列（minmax(0,1fr)），@media (min-width: 1024px) 恢复 minmax(0,3fr) minmax(0,2fr)：<1024 上下堆叠、≥1024 左右两栏，与线框一致，档位仍是既有 1024px。

### 2.8 明确没动的东西

- 转写合并三层调用点零改动：replaceTranscript(...) 的入参、transcriptSpanRef、onTranscript 回调体与 changeAnswer 逐字保持（仅文件级重写导致的换行格式最终还原为原样）。
- roomStore.ts、useInterviewRoom.ts、api/、audio/、stream/ 零 diff；结束按钮的 controller.finish() 与 loading 不变。
- 未新增依赖、未引 webfont / 动效库、未新增 token（类别徽章消费 T2 的 --br-gradient-badge，卡片消费 T2 的 --br-shadow-* 与 --br-radius-lg，进度条消费 accent 系）。

## 三、可复跑命令 + 原始输出 + 数字

### 3.1 TDD 红相（实现前，唯一一次运行记录）

命令：pnpm -C apps/web test --run src/pages/InterviewRoomPage.test.tsx

~~~
16:     × keeps the feedback timeline in submission order and highlights the newest entry 361ms
17:     × counts the answer characters from the box's own value 7ms
18:     ✓ keeps submitting disabled while the room has no current question 10ms
471: Test Files  1 failed (1)
472:      Tests  2 failed | 10 passed (12)
~~~

数字：2 例新行为单测红（反馈时间线/最新高亮、字数计数），既有 9 例绿；「无待答题目时禁用」是等价性守卫，实现前即绿（见 §五.3）。

### 3.2 守卫 ①–⑤

~~~
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0
~~~

白名单：本票两个 CSS 文件共 5 条 allow（改动前 6 条，净 -1；删掉的是旧 .progressBar 的 min-width 40px 放行，其余是等价替换）——
InterviewRoomPage.module.css:15 房间二级行分隔线 1px、:111 提示条分隔线 1px（两条都在改动前就有）；
RoomParts.module.css:11 题号列最小宽度 32px（原有）、:101 作答卡片边框 1px（原 border-top 的等价替换）、:186 步骤条高度 6px（原 .progressBar 高度的等价替换）。
仓库 apps/web/src 下 allow 总数实测 43（HEAD 为 47；差额 -4 中本票 -1，其余 -3 来自同波 AiSettingsPage 1→0 与 InterviewReportPage 3→1）。

### 3.3 前端测试

~~~
$ pnpm -C apps/web test --run src/pages/InterviewRoomPage.test.tsx
 Test Files  1 passed (1)
      Tests  12 passed (12)

$ pnpm -C apps/web test --run src/pages/VoiceWiring.test.tsx src/audio
 Test Files  6 passed (6)
      Tests  49 passed (49)

$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  197 passed (197)
~~~

数字：本票行为单测 12 例（原 9 + 新 3）全绿；转写合并与语音相关 6 文件 49 例全绿；全量 197 passed（开工基线为 187 例，其中 1 例因同波 T8 正在写红相而失败，收口时已随该票转绿；本票净增 3 例）。

### 3.4 typecheck / lint

~~~
$ pnpm -C apps/web typecheck
$ tsc --noEmit
TSC_EXIT=0
$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

### 3.5 变异证明（×1，删最新高亮的数据钩子）

命令（从仓库根跑；含空格的 --file 与 --test 都加引号）：
cd '/root/better resume' && bash scripts/verify_mutation.sh --test "pnpm -C apps/web test --run src/pages/InterviewRoomPage.test.tsx" --file '/root/better resume/apps/web/src/pages/InterviewRoomPage.tsx' --find 'data-latest={index === latestTurnIndex ? "true" : undefined}' --replace ''

~~~
sha_before=642d279df28b2f1a78638e7ca3e5ca23cd90592426543e97e19967341cf8bd46
== 1/3 baseline ==   Tests  12 passed (12)
== 2/3 mutate ==     mutated 1 occurrence in .../InterviewRoomPage.tsx
== 2/3 red ==        Tests  1 failed | 11 passed (12)
                     FAIL keeps the feedback timeline in submission order and highlights the newest entry
                     Expected the element to have attribute: data-latest="true"
                     Received: null
== 3/3 restore ==    Tests  12 passed (12)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/InterviewRoomPage.tsx)
sha_after =642d279df28b2f1a78638e7ca3e5ca23cd90592426543e97e19967341cf8bd46
CMP_OK
MUT_EXIT=0
~~~

说明：锚点是高亮态的 DOM 钩子（CSS 只认 [data-latest="true"]），删掉它等于删掉「最新」的高亮标记；变异后仅目标用例变红，恢复后 sha256 与逐字节（cmp）一致。第一版锚点选 data-latest 而测试只断言可见「最新」文本时曾假绿，随后把断言补到 data-latest 才成立（弱变异会被这一版抓出来）。

### 3.6 改动面自查

~~~
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
?? docs/tickets/p14-web-redesign/T6-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md
~~~
（本票收口时刻的快照；同波 4 票并行，其他票的行会继续变，本票只对上面 5 个源文件负责。）

~~~

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
84	6	apps/web/src/pages/InterviewRoomPage.test.tsx
46	17	apps/web/src/pages/InterviewRoomPage.tsx
25	0	apps/web/src/pages/interview/RadarChart.module.css
9	1	apps/web/src/pages/interview/ResumePreviewCard.module.css
128	19	apps/web/src/pages/interview/RoomParts.module.css
70	21	apps/web/src/pages/interview/RoomParts.tsx
~~~

**本票改动的 5 个文件**（其余条目属同波 T4/T5/T8，本票未触碰）：

- apps/web/src/pages/InterviewRoomPage.tsx（+46 / -17）：二级行、反馈分组与折叠、类别徽章接线、去掉页内 h2。
- apps/web/src/pages/InterviewRoomPage.module.css（+69 / -13）：.roomBar / .roomActions / 反馈列表与最新高亮 / 折叠开关与 body / 断点块。
- apps/web/src/pages/InterviewRoomPage.test.tsx（+84 / -6）：3 例新行为单测 + 3 条表现层断言改写 + submitView 两个可选入参（见 §五.1）。
- apps/web/src/pages/interview/RoomParts.tsx（+70 / -21）：CategoryBadge 新增；QuestionCard 的 category prop、题面字阶、要点标签；AnswerComposer 的计数器 / 快捷键 / 录音态；ProgressBar 改步骤条。
- apps/web/src/pages/interview/RoomParts.module.css（+128 / -19）：类别徽章 / 要点标签 / composer 卡片 / 录音点 / 步骤条 / reduced-motion 块。
- 本文件 docs/tickets/p14-web-redesign/T6-EVIDENCE.md（新建）。

零 diff 范围（逐条核对）：apps/web/src/api、src/audio、src/stream、src/interview/（roomStore / useInterviewRoom 等）、apps/web/src/components、src/styles、scripts/、README、T1–T10 票与既有 EVIDENCE、apps/api。

## 四、未验证项诚实清单

- **浏览器观感全未核验**：题面字号、渐变类别徽章、最新反馈高亮（描边+阴影+「最新」标签）、composer 吸底阴影与 focus-within、录音指示点动效，都没有人工/截图核验；本票按 README 当前口径不拍截图（T9 统一收口）。
- **<1024 断点行为只有静态存在性**：Vitest 未开 css，jsdom 不应用媒体查询与 CSS Modules；折叠（默认 display:none → data-open 展开）与吸底（sticky bottom:0）在真实视口的塌缩效果未核。
- **≥1024 隐藏折叠开关**（.feedbackToggle display:none）对键盘 Tab 顺序的影响未核。
- **类别徽章未写单测**：票面三条红-绿切片未点名该缝（纯查表 + 条件渲染），既有夹具也没有 category 字段；真实后端数据下的呈现未核。
- hover / active / focus-visible 手感、深色主题下的新样式未核。
- MANUAL-TESTING §1.1–1.4 实时转写 / 答题交互未手测；本票未改其语义，VoiceWiring + audio 49 例绿作为机器兜底。
- **未跑 bash scripts/verify.sh --layer all 与 apps/api 的 pytest/uv**（并发安全约定：本波 4 票并行，收口由主代理统一跑）。
- 未跑 bash scripts/compose_smoke.sh（未动部署面）。

## 五、与提案的偏差

1. **断言调整清单（3 条，全部在 InterviewRoomPage.test.tsx，均为表现层定位而非削弱）**：
   - getByText("考察要点：取舍、量化") → getByRole("list", { name: "考察要点" }) + toHaveTextContent("取舍") / ("量化")（focus_points 由顿号串改为标签，线框要求）。
   - getByText("已答 0 / 2 题") → getByText("题 1 / 2")；getByText("已答 1 / 2 题") → getByText("题 2 / 2")（线框的步骤条文案就是「题 X / Y」）。
   - 没有删除任何断言；转写/VoiceWiring 测试零改动。
2. **「反馈按时间分组」落为单一时间序分组**：数据里没有 per-turn 时间戳，拒绝伪造。若后续要按日期分组，需先有 turn 级时间字段（不在本票范围）。
3. **新增 3 例行为单测**，票面点名两条缝（反馈分组/最新高亮、composer 行为等价）；其中「无待答题目时提交与输入禁用」实现前即绿，作为既有状态驱动的等价性守卫，不构成新的红-绿切片。折叠开关的开合（aria-expanded）断言并进反馈用例，未单立缝。
4. **窄屏折叠用 Button + data-open 自实现**，未复用 Collapsible（无法在 ≥1024 只隐掉开关）、未用 <details>（闭包内容在宽屏强制展开不可靠）。这带来一个页面级 UI state（feedbackOpen），仅控制可见性，不参与提交/禁用语义。
5. **页内 h2「模拟面试」移除**：页壳顶栏是唯一品牌位，线框二级行只列步骤条 / 类别徽章 / 结束按钮。既有测试未断言该标题。
6. **placeholder 文案由「用具体案例回答（Ctrl/Cmd + Enter 提交）」改为「用具体案例回答」**，快捷键提示改为常显一行（线框要求「快捷键提示」，避免同一提示出现两处）。
7. **QuestionCard 新增可选 category prop**：roomStore 的 InterviewTurn 不含 category，为避免改数据层，由页面把 state.currentQuestion.category 直接传下去；该 prop 可选，其他调用点与测试无需变更。
8. 进度条由「宽度百分比 + 已答 X / Y 题」改为「一题一格 + 题 X / Y」，删掉了原 .progressBar 的 min-width allow 行；旧的 progressBar class 无其他引用，未留死代码。
