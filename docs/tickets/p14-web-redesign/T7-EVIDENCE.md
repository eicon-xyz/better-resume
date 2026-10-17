# P14-T7 验收包 — 聊天页（并入页壳 + 会话侧栏二级化 + composer 复用）

- 票面：docs/tickets/p14-web-redesign/T7-chat-page.md
- 线框依据：docs/tickets/p14-web-redesign/README.md §1.4「聊天页」、§1.5 视觉语言
- 基线：HEAD=1047bd1（工作区含同波 T4/T5/T6/T8 已收口的未提交改动；本票改动全留工作区，未 commit）
- 唯一写入路径：ChatPage.tsx / .module.css / .test.tsx、pages/chat/（SessionSidebar / MessageList / Composer / MessageBubble）

## 一、意图复述

在不改业务逻辑、数据流、TanStack Query / zustand 用法、REST 契约与路由表的前提下，把聊天页按线框收进页壳并复用既有视觉配方：

1. 页壳：页内不再重复品牌 / 导航 / 退出；模型选择落主区头；「AI 设置」由顶栏主导航承担。
2. 会话侧栏：保持页内二级栏形态与 <1024 折叠，hover / active / 选中态沿用 T10 的 token 交互态。
3. 消重复：pages/chat 内的卡片配方收敛为一份共享类。
4. composer：复用面试间的卡片化配方（字数计数、语音按钮录音态、快捷键提示）。
5. 空态：沿用既有 Empty 组件，并在主区居中。

红线：Composer 的 replaceTranscript 合并链（spanRef / valueRef 的 prop effect）、MessageList 的流式渲染、useChatStream / useSession / store / selectors、src/stream、src/audio 零语义改动；VoiceWiring 与 Composer 两个测试文件的既有断言一字未改。

## 二、实现决定交代

### 2.1 模型选择落点：主区头（顶栏右侧不可达）

- 线框允许「主区头」或「顶栏右侧」二选一，本票选主区头：顶栏在 apps/web/src/components/AppShell.*，不在本票写入路径内；且模型是当前会话的上下文操作，不是全局导航（全局三项导航在顶栏）。
- 落点为 main 内的 .contextBar（右对齐一行），只承载「模型 + Select」；未新增第二处模型控件，功能未删。
- 「AI 设置」由 AppShell 顶栏主导航承担、退出在顶栏用户区；读 HEAD 版 ChatPage.tsx 确认页内本就没有这两项，本票未在页内重复。

### 2.2 页内 header 与 h2

- 删除页内 header、h2「对话」与其 1px 底部分隔线：顶栏主导航已用 aria-current=page 表达当前页（AppShell），页内再放一份标题属重复；README §1.4 聊天页线框只要求「并入页壳顶栏」，未列标题行。
- 这是本票对线框的一处解释性取舍，已在 §五 单列，待确认。

### 2.3 会话侧栏

- SessionSidebar.module.css 零改动：hover（surface-raised + border）、:active（accent-muted）、选中 .active（accent 描边 + accent-muted 底）、summary / 删除键 hover 均为 T10 已定的 token 交互态，核对成立。
- 新增 aria-current=true 于当前会话按钮：把「选中」从纯 class 变成可观察、可被读屏播报的状态；不改点击 / 新建 / 删除行为（onSelect / onCreate / onDelete 原样）。
- 页内二级栏形态与 <1024 折叠（details / summary + 横向滚动）保持原样。

### 2.4 卡片配方收敛（pages/chat 内）

- 共享类 .card 落在 Composer.module.css：display / flex-direction / gap / padding / 1px 描边 / --br-radius-lg / --br-color-surface-raised。
- Composer.module.css 的 .composer 用 composes: card 取这份配方，再叠 margin、--br-shadow-sticky、focus-within（描边转 accent + --br-shadow-md）与 transition。
- MessageBubble.module.css 的 .bubble 用 composes: card from ./Composer.module.css 取同一份配方，只保留 max-width 与左右对齐修饰；用户气泡底色用 .bubble.user 提高特异性，不依赖跨文件声明顺序。
- 收敛范围严格限定 pages/chat：README §1.2 点名的另两处复制（interview/RoomParts、InterviewReportPage）在本票写入路径之外；把配方提到 components/ 属「动共享层」，按红线不做，已在 §五 报告。

### 2.5 composer 卡片化

- 卡片：描边 1px + --br-radius-lg + --br-color-surface-raised + --br-shadow-sticky + focus-within 转 accent，transition 在 prefers-reduced-motion 下同选择器重访。
- 未叠 position: sticky：聊天主区的 composer 已是 flex 列里 .messages 之外的固定底栏，sticky 在非滚动父级内无实际作用；卡片其余配方与面试间一致。
- 字数：value.trim().length，渲染「N 字」；不引入任何新状态，直接由输入框自身 value 推导。
- 快捷键提示：常显「Enter 发送，Shift+Enter 换行」，与 placeholder 去重（placeholder 改回「问点什么…」）。这里是聊天页真实的按键语义（Enter 提交，Shift+Enter 换行），未照抄面试间的 Ctrl / ⌘ + Enter。
- 语音按钮：recording 时切 secondary + aria-pressed=true + data-recording=true + 引点（--br-color-danger，reduced-motion 下 animation: none）；可访问名仍是「语音输入」/「停止录音」。
- 提交 / 禁用：仍是 disabled || value.trim().length === 0 与「空文本不提交」的既有语义，零改动。

### 2.6 空态与主区布局

- MessageList 空态直接返回既有 Empty（标题「还没有消息」+ 按 streaming 切换的描述），外面包一层 .empty 让它在主区垂直居中；.messages 改为 flex 列以提供居中所需的可伸展高度。
- 未新增空态文案或按钮，未改 Empty 组件。

### 2.7 明确没动的东西

- Composer.tsx 的 update / prop effect（replaceTranscript(valueRef.current, spanRef.current, transcript)）/ submit / handleKeyDown、transcriptSpanRef 链路逐字保持；只在其外围增删展示层 JSX。
- MessageBubble.tsx、MessageList 的流式渲染与折叠状态、SessionSidebar 的回调、ChatPage 的 stream / query / store 接线零改动。
- 未新增依赖、未引 webfont / 动效库、未新增 token（只用现有 47 个：surface-raised / border / radius-lg / shadow-sticky / shadow-md / duration-fast / duration-normal / space-* / text-xs / accent / danger / accent-muted / radius-pill）。

## 三、可复跑命令 + 原始输出 + 数字

环境：
~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
~~~
前端命令从仓库根跑。

### 3.1 TDD 红相（实现前）

命令：pnpm -C apps/web test --run src/pages/chat/Composer.test.tsx src/pages/ChatPage.test.tsx

~~~text
FAIL  src/pages/ChatPage.test.tsx > ChatPage > marks the open session in the sidebar as the current one
FAIL  src/pages/chat/Composer.test.tsx > chat composer 卡片 > counts the characters from the box's own value
FAIL  src/pages/chat/Composer.test.tsx > chat composer 卡片 > shows the keyboard shortcut and the recording state on the voice button
 Test Files  2 failed (2)
      Tests  3 failed | 11 passed (14)
~~~

数字：3 例新行为单测红（侧栏 aria-current、字数计数、快捷键 + 录音态）；「空文本禁用发送」与「/chat 无会话时不标 aria-current」实现前即绿（§五.4）。

### 3.2 守卫①–⑤与白名单

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0
$ grep -rn 'allow:' apps/web/src | wc -l
41
~~~

数字：守卫 exit 0；allow 实测 41（开工 43，净 -2，未新增）：删除 ChatPage.module.css 旧 .header 的 1px 分隔线放行；MessageBubble 的 1px 气泡描边放行随声明并入共享类（该放行即 Composer.module.css 里卡片描边那条，条数不增）。SessionSidebar 的 4 条与 MessageBubble 的 3 条（max-width / 光标宽 / 光标间距）原样保留。

### 3.3 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  202 passed (202)

$ pnpm -C apps/web typecheck
$ tsc --noEmit
TSC_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：全量 202 passed（开工基线 197，本票净增 5）；typecheck / lint 均 exit 0。

### 3.4 转写 / SSE 语义面

命令：pnpm -C apps/web test --run src/pages/VoiceWiring.test.tsx src/pages/chat/Composer.test.tsx src/audio src/chat src/stream

~~~text
 Test Files  11 passed (11)
      Tests  77 passed (77)
~~~

既有断言零改动核对：

~~~text
$ git diff --stat -- apps/web/src/pages/VoiceWiring.test.tsx apps/web/src/audio apps/web/src/chat apps/web/src/stream apps/web/src/api
(空输出)
$ git diff -U0 -- apps/web/src/pages/chat/Composer.test.tsx | grep -E '^-[^-]'
(空输出)
~~~

数字：11 文件 77 例全绿；VoiceWiring / audio / chat / stream / api 零 diff；Composer.test.tsx 只有新增行、无删除行。

### 3.5 变异证明（×1，删字数计数节点）

命令（从仓库根跑；--find 里的花括号为字面文本）：
~~~bash
cd '/root/better resume'
bash scripts/verify_mutation.sh --test "pnpm -C apps/web test --run src/pages/chat/Composer.test.tsx" --file '/root/better resume/apps/web/src/pages/chat/Composer.tsx' --find '<span className={styles.counter}>{characters} 字</span>' --replace ''
~~~

~~~text
sha_before=9c62a67c056678c5494165b4255f9d4353f2f7217d93483fc9d660fa3b409a5c
== 1/3 baseline ==   Tests  6 passed (6)
== 2/3 mutate ==     mutated 1 occurrence in .../Composer.tsx
== 2/3 red ==        Tests  1 failed | 5 passed (6)
                     FAIL counts the characters from the box's own value
                     Unable to find an element with the text: 0 字
== 3/3 restore ==    Tests  6 passed (6)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/chat/Composer.tsx)
sha_after =9c62a67c056678c5494165b4255f9d4353f2f7217d93483fc9d660fa3b409a5c
CMP_OK
MUT_EXIT=0
~~~

### 3.6 共享类在真实构建下成立（非票面命令，为 composes 补证）

composes 跨文件在 Vitest（css: false）里不编译，故补跑一次生产构建核对：

~~~text
$ pnpm -C apps/web build
✓ 400 modules transformed.
✓ built in 425ms
BUILD_EXIT=0
~~~

构建产物里的类映射与 CSS 规则：

~~~text
bubble: "_bubble_yaq8r_1 _card_443fg_2"
composer: "_composer_443fg_14 _card_443fg_2"
_card_443fg_2 规则在 CSS 中出现 1 次
~~~

数字：MessageBubble 与 Composer 都带上同一个 .card 哈希类，.card 规则只产出 1 份。

### 3.7 改动面自查

~~~text
$ git status --porcelain
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/AiSettingsPage.test.tsx
 M apps/web/src/pages/AiSettingsPage.tsx
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/ChatPage.test.tsx
 M apps/web/src/pages/ChatPage.tsx
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewIntroPage.test.tsx
 M apps/web/src/pages/InterviewIntroPage.tsx
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewReportPage.test.tsx
 M apps/web/src/pages/InterviewReportPage.tsx
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/InterviewRoomPage.test.tsx
 M apps/web/src/pages/InterviewRoomPage.tsx
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/Composer.test.tsx
 M apps/web/src/pages/chat/Composer.tsx
 M apps/web/src/pages/chat/MessageBubble.module.css
 M apps/web/src/pages/chat/MessageList.module.css
 M apps/web/src/pages/chat/MessageList.tsx
 M apps/web/src/pages/chat/SessionSidebar.tsx
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/pages/interview/RoomParts.tsx
?? docs/tickets/p14-web-redesign/T4-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T5-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T6-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md
（ChatPage.* 与 chat/* 共 10 行为本票；其余 M 行属同波 T4/T5/T6/T8，本票未触碰）
~~~

本票 10 个文件的 git diff --numstat：

~~~text
6	16	apps/web/src/pages/ChatPage.module.css
16	0	apps/web/src/pages/ChatPage.test.tsx
20	23	apps/web/src/pages/ChatPage.tsx
72	6	apps/web/src/pages/chat/Composer.module.css
38	0	apps/web/src/pages/chat/Composer.test.tsx
37	22	apps/web/src/pages/chat/Composer.tsx
3	9	apps/web/src/pages/chat/MessageBubble.module.css
8	0	apps/web/src/pages/chat/MessageList.module.css
6	4	apps/web/src/pages/chat/MessageList.tsx
1	0	apps/web/src/pages/chat/SessionSidebar.tsx
~~~

逐文件说明：
- ChatPage.tsx（+20 / -23）：页内 header 换成 .contextBar，只留模型控件；删 h2 与 headerControls。
- ChatPage.module.css（+6 / -16）：.header / .title / .headerControls 换成 .contextBar；.messages 改 flex 列。
- ChatPage.test.tsx（+16 / -0）：2 例侧栏 aria-current 行为单测（追加，无删除行）。
- chat/Composer.tsx（+37 / -22）：字数、快捷键提示、footer 容器、录音态 data-recording + 引点；placeholder 去重。合并链零改动。
- chat/Composer.module.css（+72 / -6）：共享 .card、composer 卡片、footer / 提示 / 计数 / 引点与 reduced-motion。
- chat/Composer.test.tsx（+38 / -0）：3 例 composer 行为单测（追加，无删除行）。
- chat/MessageBubble.module.css（+3 / -9）：.bubble 改为 composes 共享 .card；用户气泡底色提高特异性。
- chat/MessageList.tsx（+6 / -4）：空态外包 .empty 容器。
- chat/MessageList.module.css（+8 / -0）：.empty 居中样式。
- chat/SessionSidebar.tsx（+1 / -0）：当前会话按钮加 aria-current。
- 本文件 docs/tickets/p14-web-redesign/T7-EVIDENCE.md（新建）。

零 diff 范围（逐条核对）：apps/web/src/components、src/styles、src/api、src/audio、src/stream、src/chat、src/interview、apps/web/src/pages/interview（属 T6）、scripts/、README、T1–T10 票与既有 EVIDENCE、apps/api。

## 四、未验证项诚实清单

- 浏览器观感全未核验：卡片吸底阴影与 focus-within、录音引点动效、气泡与 composer 同配方的观感、用户气泡底色、contextBar 右对齐、空态居中都未人工 / 截图核验；本票按当前口径不拍截图（T9 统一收口）。
- composes 的运行时视觉只有构建期证据（类映射与 CSS 规则），浏览器里气泡实际取到共享卡片样式未核。
- <1024 断点行为只有静态存在性：Vitest 未开 css，jsdom 不应用媒体查询；侧栏折叠与定宽列未在真实视口核。
- hover / active / focus-visible 手感与深色主题下的新样式未核。
- aria-current=true 的读屏播报未核（机器只断言属性）。
- 未跑 bash scripts/verify.sh --layer all 与 apps/api 的 pytest / uv（并发安全约定：本波多票并行，收口由主代理统一跑）。
- 未跑 bash scripts/compose_smoke.sh（未动部署面）。

## 五、与提案的偏差

1. 删除页内 h2「对话」：顶栏主导航已用 aria-current 表达当前页，README §1.4 聊天页线框未列标题行；这只涉及标题展示，改动前后 ChatPage.test.tsx 均无相关断言。属解释性取舍，需用户确认。
2. 模型选择落主区头：顶栏在 components/AppShell 内、不在写入路径，且模型是会话上下文操作；线框允许的两个落点只选了其一，未两处都放、未删功能。
3. composer 未叠 position: sticky：聊天页 composer 已是 flex 列固定底栏，sticky 无实际作用；描边 / 圆角 / 吸底阴影 / focus-within 照面试间配方。
4. 新增 5 例单测：3 例真红-绿（字数计数、快捷键 + 录音态、侧栏 aria-current），1 例 aria-current 的反向断言（/chat 无会话时不标）实现前即绿，1 例「空文本禁用发送」是既有行为的等价性守卫、实现前即绿。后两例是等价性守卫，不构成新的红-绿切片。
5. 快捷键提示文案取聊天页真实按键「Enter 发送，Shift+Enter 换行」，未照抄面试间的「Ctrl / ⌘ + Enter 提交」；Enter 提交语义零改动。
6. allow 白名单：票面口径写 43，实测 41（净 -2，未新增，明细见 §3.2）。
7. 跨页样式重复（interview/RoomParts 与 InterviewReportPage 的 badge / composer）未在本票收敛：这两处在写入路径之外，把配方提到 components/ 属「动共享层」，按红线不做；本票只收敛 pages/chat 内的复制。
