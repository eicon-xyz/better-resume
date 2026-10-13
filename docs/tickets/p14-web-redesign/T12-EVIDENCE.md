# P14-T12 验收包 — 对话页/首页改版 v2（通栏贴边 + 侧栏升级 + 空态 hero）

- 票面：docs/tickets/p14-web-redesign/T12-chat-redesign.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.5 / §4.1 / §4.3；T3 / T7 / T10-EVIDENCE；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）
- 基线：HEAD 含 T1–T10 已入库（工作区另有 T11 LoginGate 未提交改动，本票未触碰）

## 一、意图复述

在不改业务逻辑、数据流、REST 契约与路由表的前提下，把对话页按线框 v2 收口：

1. **通栏贴边**：对话页内容通栏——会话侧栏贴窗口左缘（宽 300px，保留页内二级栏语义与 <1024 顶部折叠），主区占余下宽度；主区内部消息列与 composer 可读宽度 860px 居中。机制是 AppShell 内容容器新增通栏变体，不使用负边距 / 100vw 逃逸。
2. **侧栏升级**：顶部「＋ 新建对话」主按钮 + 本地搜索框（大小写不敏感子串、纯前端零 API）+ 会话行（标题 / 次行 / 相对时间 / 选中态渐变左边条 + accent-muted 弱底 / hover 删除）+ 无结果文案。
3. **空态主区**：hero = 问候语 + 一行说明 + 6 个建议 chips（点击把文案填入输入框）+ 行动卡（跳 /interview）；有消息时让位于消息列。
4. **主区头**：左侧会话标题（有会话时），右侧模型 Select 保留现状。
5. 消息列 / composer 的 T7 配方不动；可选的日期分隔线本票未做。

## 二、实现决定交代

### 2.1 通栏走 AppShell 容器变体

- AppShell 内容容器保留原 `.content`（max-width 1200 + 居中 + ≥1024 水平内边距），新增 `.contentFull`（`max-width: none; margin: 0;`，≥1024 `padding: 0`），在对话页路由下与 `.content` 同时挂上。
- 启用判定用 AppShell 已有的 `isActive(pathname, "/chat")`（与导航高亮同一份判定），未加 prop 或 context：App.tsx 不在本票写入路径，ChatPage 无法向上传 prop；路由判定同时避免首帧先收窄再通栏的闪动。
- 未使用负边距 / `width: 100vw` / `calc(50% - 50vw)`；`.contentFull` 只是取消容器上限与内边距，可读宽度由页内自己控制。
- 顶栏、导航、用户区结构零改动。

### 2.2 数值与可读宽度

- 侧栏宽度：SessionSidebar.module.css 的定宽列由 260px 改为 300px，仍复用同一行 `/* allow: 会话侧栏固定宽度（300px 版式几何） */`，allow 条数不变。
- 可读宽度：`styles/tokens.css` 新增一行 `--br-width-measure: 860px`（非主题族尺寸 token，无需深色重述），消费 4 处——MessageList 的 `.empty` / `.list` / `.actionCard` 与 Composer 的 `.composer`。
- 消息滚动容器（`.messages`）仍通栏，`.list` 在容器内 860px 居中；composer 用 `width: calc(100% - 2 × space-4)` + `max-width: 860px` + `margin-inline: auto`，窄屏保留两侧 16px 间隙。
- 断点仍只有 1024px 一档；侧栏 <1024 的 details 折叠与 ≥1024 定宽列语义未改。

### 2.3 侧栏升级

- 搜索：`useState` + `useMemo` 纯前端过滤，匹配 `title || "未命名会话"` 的大小写不敏感子串（query 先 trim）；清空即恢复全量；仅在过滤生效且无匹配时渲染「没有匹配的会话」。
- 会话行：标题一行 + 次行（相对时间 + 既有消息数角标）；选中态仍是 T10 的 accent-muted 弱底 + accent 描边，另加 `::before` 渐变左边条（宽 `--br-space-1` = 4px，取 `--br-gradient-hero`，不新增尺寸 token）。
- hover 删除键与 summary hover 原样保留；过渡仍为 `--br-duration-fast`，reduced-motion 同选择器覆盖。

### 2.4 空态 hero 与 chips 接线

- 空态仍用既有 Empty（标题「还没有消息」保留，既有断言不改），hero / chips / 行动卡落在 Empty 的 `action` 槽；streaming 时描述仍是「正在生成第一条回答…」。
- chips 只调 ChatPage 传入的 `onSuggestion(text)`：清空转写 span、写 `draftRef` 与 `draft` state，经既有 Composer 的 transcript 合并链填进输入框——没有新增 Composer 状态、没有新 API。
- 行动卡调 `onStartInterview()`，由 ChatPage `navigate("/interview")`，纯路由。
- 文案逐字照用批准稿（问候语 / 说明 / 6 个 chips / 行动卡标题与说明与按钮 / 搜索 placeholder / 空结果）。

### 2.5 主区头

- contextBar 左侧新增会话标题 `h2`（取当前路由会话的 title，空则「未命名会话」），`margin-right: auto` 把它推到左侧；右侧模型 Select 与 label 原样保留。

### 2.6 未动的配方

- Composer.tsx 与 MessageBubble.tsx / MessageBubble.module.css 零改动；Composer.module.css 只加 width / max-width / margin-inline 三行。
- MessageList 的流式渲染、折叠状态、加载更早消息逻辑未改；只在空态分支与 props 上增量。
- 未新增依赖、未引组件库 / webfont / 动效库；未动路由表、REST 契约、`src/api`、`src/chat` 语义层、`src/stream`、`src/audio`。

### 2.7 相对时间

- 新增纯函数 `apps/web/src/pages/chat/relativeTime.ts`（注入 now，便于确定性单测）：< 1 分钟「刚刚」、< 1 小时「N 分钟前」、< 1 天「N 小时前」、< 7 天「N 天前」、再往前取日期前 10 位。
- 侧栏挂载时惰性读一次时钟（`useState(() => Date.now())`）：相对时间是展示口径，不随渲染跳动，同时满足仓库 eslint 的 react-hooks/purity 与 set-state-in-effect 两条规则。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行，前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
~~~

### 3.1 TDD 红相（实现前）

命令：pnpm -C apps/web test --run src/pages/ChatPage.test.tsx src/components/AppShell.test.tsx src/pages/chat/relativeTime.test.ts

~~~text
 ✓ marks the nav item of the current route with aria-current 232ms
 ✓ keeps the section highlighted on a nested route 30ms
 × makes the content container full-bleed on the chat route 12ms
 ✓ keeps the content container constrained outside the chat route 12ms
 ...（既有 7 例 ChatPage 用例全绿）...
 × fills the composer with the suggestion when a chip is clicked 1012ms
 × routes to the interview page from the empty-state action card 1008ms
 × filters the loaded sessions by a case-insensitive substring and restores on clear 38ms
 × shows the empty-result copy when the search matches nothing 28ms
 FAIL  src/pages/chat/relativeTime.test.ts
 Error: Failed to resolve import "./relativeTime" from "src/pages/chat/relativeTime.test.ts". Does the file exist?
 Test Files  3 failed (3)
      Tests  5 failed | 11 passed (16)
~~~

红相点名的失败原因（逐条）：AppShell 内容容器无 `.contentFull`（Received: _content_17e458）；找不到 button「出一套项目深挖题」；找不到 button「去上传」；找不到 label「搜索会话」（两例）；relativeTime 模块不存在。

### 3.2 守卫与白名单

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0

$ grep -rn 'allow:' apps/web/src | wc -l
41
~~~

数字：退出码 0；扫描 27 个 .css；违规 0；末行 ok；`allow:` 白名单 41 条，与开工基线逐条相同、新增 0（本票只改了 SessionSidebar 那条 260px → 300px 的取值）。

可读宽度走 token 的消费清单（验收 1 的二选一：选 token，未新增 allow）：

~~~text
apps/web/src/styles/tokens.css:64:  --br-width-measure: 860px;
apps/web/src/pages/chat/Composer.module.css:17:  max-width: var(--br-width-measure);
apps/web/src/pages/chat/MessageList.module.css:8:  max-width: var(--br-width-measure);
apps/web/src/pages/chat/MessageList.module.css:68:  max-width: var(--br-width-measure);
apps/web/src/pages/chat/MessageList.module.css:83:  max-width: var(--br-width-measure);
~~~

数字：`--br-width-measure` 定义 1 处（tokens.css:64）、消费 4 处（Composer 1 + MessageList 3）；全部引用可解析，G1/G2 通过。

### 3.3 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  27 passed (27)
      Tests  210 passed (210)
VITEST_EXIT=0

$ pnpm -C apps/web typecheck
$ tsc --noEmit
TSC_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：27 文件 / 210 例全绿（开工基线 26 / 202，本票净增 1 文件 / 8 例，只增不减）；typecheck 与 lint 退出码 0。

### 3.4 新增行为单测清单（8 例）

~~~text
src/pages/ChatPage.test.tsx（+4）
  fills the composer with the suggestion when a chip is clicked
  routes to the interview page from the empty-state action card
  filters the loaded sessions by a case-insensitive substring and restores on clear
  shows the empty-result copy when the search matches nothing
src/components/AppShell.test.tsx（追加 2，既有 2 例未改）
  makes the content container full-bleed on the chat route
  keeps the content container constrained outside the chat route
src/pages/chat/relativeTime.test.ts（+2，新文件）
  reads recent timestamps as 刚刚 / 分钟前 / 小时前
  falls back to days and then to the calendar date
~~~

断言口径：chips 例断言输入框（aria-label 输入消息）的 value；搜索例断言会话按钮的存在/消失（按可访问名）与空结果文案；行动卡例断言路由目标渲染；AppShell 变体例断言内容容器的类名（CSS Modules 在 Vitest 下输出哈希类名，测试与实现取同一模块导出）；相对时间例断言注入 now 后的纯函数返回值。

### 3.5 变异证明（删 chips 填入的状态更新）

命令（从仓库根跑）：

~~~bash
bash scripts/verify_mutation.sh \
  --test "pnpm -C apps/web test --run src/pages/ChatPage.test.tsx" \
  --file '/root/better resume/apps/web/src/pages/ChatPage.tsx' \
  --find '              draftRef.current = text;
              setDraft(text);' \
  --replace '              draftRef.current = text;'
~~~

~~~text
== 1/3 baseline ==   Tests 12 passed (12)
== 2/3 mutate ==     mutated 1 occurrence in /root/better resume/apps/web/src/pages/ChatPage.tsx
== 2/3 red ==        Tests 1 failed | 11 passed (12)
                     × fills the composer with the suggestion when a chip is clicked
                     expect(element).toHaveValue(出一套项目深挖题)
                     Received: (空)
== 3/3 restore ==    Tests 12 passed (12)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/ChatPage.tsx)
MUT_EXIT=0
sha_before=e9663cc2dcc13aa015a8e8794fc38f95d96b57a1bdd39b7491c23c9299847d01
sha_after =e9663cc2dcc13aa015a8e8794fc38f95d96b57a1bdd39b7491c23c9299847d01
CMP_OK
~~~

数字：基线绿 → 变异红（只有 chips 这一例红，其余 11 例仍绿，说明锚点精确）→ 恢复绿；恢复后 sha256 与变异前一致，`cmp` 逐字节相同；`--file` 用绝对路径。锚点是「chip 点击写 draft state」的真实现，删掉后输入框保持空值——不是拼写类弱变异。

### 3.6 verify --layer all

~~~text
$ bash scripts/verify.sh --layer all
[1/17] cd apps/api && uv run pytest --cov=... → 997 passed, 3 warnings
[2/17] check_coverage_floors.py → floors ok（TOTAL 6553 stmts / 305 miss / 95%）
[3/17] pnpm -C apps/web exec vitest run → 27 passed (27) / 210 passed (210)
[4/17] cd apps/api && uv run ruff check . → All checks passed!
[5/17] cd apps/api && uv run ruff format --check . → 268 files already formatted
[6/17] alembic upgrade head → ok
[7/17] alembic check → No new upgrade operations detected.
[8/17] export_openapi.py --check → openapi.json is up to date
[9/17] extract_api_index.py --check → API index is up to date
[10/17] pnpm -C apps/web lint → exit 0
[11/17] pnpm -C apps/web typecheck → exit 0
[12/17] pnpm -C apps/web check:api → schema.d.ts 无 diff
[13/17] python3 scripts/check_web_style_guards.py → ok (27 css file(s))
[14/17] pytest tests/test_fault_probe.py ... → 101 passed, 2 warnings
[15/17] bash -n scripts/*.sh → shell syntax ok
[16/17] check_scripts.py → script syntax ok (24 python scripts)
[17/17] verify_audit_evidence.py --structural → structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T144512Z-all
VERIFY_ALL_EXIT=0
~~~

数字：17 条命令全过、末行 ALL PASS、退出码 0；API 997 passed；coverage floors 过（TOTAL 95%）；web 210 passed；契约三件套（openapi / api-index / schema.d.ts）零 diff；守卫绿。

### 3.7 布局数值（通栏实证：未实测，仅推算）

实测基线（本票前，视口 1344）：content x=72 w=1200 → page w=1152 → sidebar 260 + main 892。
本票后推算（/chat，未在真实浏览器量过）：`.contentFull` 取消 1200 上限与内边距 → content x=0 w=1344 → page w=1344 → sidebar 300 + main 1044；消息列与 composer 取 860px 居中 → 主区内两侧留白 (1044 − 860) / 2 = 92px。
其他路由（/interview、/settings/ai 等）不变，仍是 content x=72 w=1200。

### 3.8 改动面自查

~~~text
$ git status --porcelain
 M apps/web/src/components/AppShell.module.css
 M apps/web/src/components/AppShell.test.tsx
 M apps/web/src/components/AppShell.tsx
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/ChatPage.test.tsx
 M apps/web/src/pages/ChatPage.tsx
 M apps/web/src/pages/LoginGate.module.css
 M apps/web/src/pages/LoginGate.tsx
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/MessageList.module.css
 M apps/web/src/pages/chat/MessageList.tsx
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/chat/SessionSidebar.tsx
 M apps/web/src/styles/tokens.css
?? apps/web/src/pages/chat/relativeTime.test.ts
?? apps/web/src/pages/chat/relativeTime.ts
?? docs/design/chat/
?? docs/design/interview-room/
?? docs/design/login-gate/
?? docs/design/report/
?? docs/design/settings/
?? docs/design/shell/
?? docs/design/upload/
?? docs/tickets/p14-web-redesign/T11-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T11-login-gate.md
?? docs/tickets/p14-web-redesign/T12-chat-redesign.md

$ git diff --numstat
10	0	apps/web/src/components/AppShell.module.css
18	0	apps/web/src/components/AppShell.test.tsx
5	1	apps/web/src/components/AppShell.tsx
8	0	apps/web/src/pages/ChatPage.module.css
79	2	apps/web/src/pages/ChatPage.test.tsx
13	0	apps/web/src/pages/ChatPage.tsx
57	1	apps/web/src/pages/LoginGate.module.css
34	30	apps/web/src/pages/LoginGate.tsx
3	1	apps/web/src/pages/chat/Composer.module.css
78	1	apps/web/src/pages/chat/MessageList.module.css
47	2	apps/web/src/pages/chat/MessageList.tsx
36	11	apps/web/src/pages/chat/SessionSidebar.module.css
64	36	apps/web/src/pages/chat/SessionSidebar.tsx
3	0	apps/web/src/styles/tokens.css
~~~

逐文件说明（本票 13 个已跟踪文件 + 3 个新文件）：

- `apps/web/src/components/AppShell.tsx`（+5 −1）：通栏判定 + 内容容器类名拼接。
- `apps/web/src/components/AppShell.module.css`（+10）：新增 `.contentFull`（含 ≥1024 padding: 0）。
- `apps/web/src/components/AppShell.test.tsx`（+18 −0）：追加 2 例变体行为用例 + 类名常量，既有 2 例一字未改。
- `apps/web/src/pages/ChatPage.tsx`（+13）：会话标题来源、contextBar 标题、MessageList 的 onSuggestion / onStartInterview 接线。
- `apps/web/src/pages/ChatPage.module.css`（+8）：`.sessionTitle`。
- `apps/web/src/pages/ChatPage.test.tsx`（+79 −2）：4 例新行为单测 + fakeClient 的 sessions 选项 + 测试路由加 /interview；删除的 2 行是 fakeClient 签名与 listChatSessions stub 的改写，无断言行被删。
- `apps/web/src/pages/chat/SessionSidebar.tsx`（+64 −36）：搜索框、新建主按钮、两行会话行 + 相对时间、空结果文案。
- `apps/web/src/pages/chat/SessionSidebar.module.css`（+36 −11）：会话行两行布局、`.sessionMeta` / `.time` / `.emptyResult`、选中态渐变左边条、300px 定宽。
- `apps/web/src/pages/chat/MessageList.tsx`（+47 −2）：空态 hero / chips / 行动卡与两个新 props。
- `apps/web/src/pages/chat/MessageList.module.css`（+78 −1）：860px 居中、hero / chips / 行动卡样式与 reduced-motion。
- `apps/web/src/pages/chat/Composer.module.css`（+3 −1）：可读宽度居中（TSX 零改动）。
- `apps/web/src/styles/tokens.css`（+3）：新增 `--br-width-measure: 860px` 一行（含注释）。
- `apps/web/src/pages/chat/relativeTime.ts` / `relativeTime.test.ts`（新建，未跟踪）：相对时间纯函数与其单测。
- `docs/tickets/p14-web-redesign/T12-chat-redesign.md`（新建，未跟踪）：本票票面；`T12-EVIDENCE.md`（本文件，新建）。

同一工作区里的其他行属前票：`LoginGate.tsx` / `LoginGate.module.css`（T11 未提交改动）、`docs/design/*`（T11 截图目录）、`T11-EVIDENCE.md` / `T11-login-gate.md`（T11 材料）——本票未触碰。

既有断言零改动核对：

~~~text
$ git diff -U0 -- apps/web/src/pages/ChatPage.test.tsx apps/web/src/components/AppShell.test.tsx | grep -E '^-[^-]'
-function fakeClient(options: { authenticated?: boolean; history?: ChatMessageView[] } = {}): FakeClient {
-    listChatSessions: () => Promise.resolve([SESSION]),
GREP_EXIT=0
~~~

数字：删除行只有 2 行，都是测试辅助的改写（fakeClient 签名加 sessions 选项、listChatSessions stub 改为读该选项），没有任何断言行被删或改。

零 diff 范围（逐条核对）：`apps/web/src/api`、`src/chat`、`src/stream`、`src/audio`、`src/pages/chat/Composer.tsx`、`MessageBubble.*`、`apps/web/src/App.tsx`、路由表、`package.json`、`scripts/`、README、T1–T11 票与既有 EVIDENCE、`apps/api`。

## 四、未验证项诚实清单

- **通栏贴边未在浏览器实测**：本会话的浏览器桥未连接任何浏览器（browser_use 返回 No browser extension is connected），3.7 的 x / w 全是按 CSS 推算，不是量出来的；`docs/design/` 的截图由用户手拍。
- hover / active / focus 手感、选中态渐变左边条的可见度、chips 的 `thin` 边框观感、空态 hero 在 860px 内的换行与居中、行动卡在 Empty 虚线框内的观感，均未人工核验。
- 深色主题下新增样式（渐变左边条、chips、hero）未人工核对；只保证引用的 token 在深色块有定义（G1b 静态校验）。
- <1024 的侧栏折叠、300px 定宽列、860px 居中在真实视口的塌缩未核（jsdom 不应用媒体查询与伪类）。
- `border: thin solid` 渲染为 1px 未实测（依据是 CSS 关键字语义与主流实现默认值，沿用 T11 的写法）。
- 相对时间只在注入 now 的纯函数单测里核过（UTC 边界：刚过 1 分钟 / 1 小时 / 1 天 / 7 天）；真实时区、跨天与「时钟挂载后不再刷新」的长时间驻留表现未核。
- 登录门渐变含顶栏铺满与顶栏透明叠层的观感未人工核验。
- 未跑 `bash scripts/compose_smoke.sh`（未改部署面与构建产物；README §4.3 的回归底线之一）。
- MANUAL-TESTING §1.1–1.4 的实时转写 / 答题交互未手测；本票未改 Composer.tsx、转写合并语义与 `src/audio`。
- 无视觉快照测试（本阶段明确不引）。

## 五、与提案的偏差

1. **会话行次行为「相对时间 + 既有消息数角标」，不做「末条消息预览一行」（已经用户确认，2026-10-13）**：会话列表 `ChatSessionView`（apps/api/src/better_resume/chat/models.py:30-37）与生成类型 apps/web/src/api/schema.d.ts:483-504 都没有 preview / last_message 字段；本包红线是零新 API，故未伪造预览。真预览（末条消息）属 M2 契约扩展（列表接口加字段）。
2. **通栏启用方式取路由判定而非 prop / context**：App.tsx 不在写入路径、ChatPage 无法向 AppShell 传 prop；用 AppShell 已有的 pathname 判定可避免首帧收窄再通栏的闪动。效果等价于「对话页启用通栏」。
3. **新增 token 落在 styles/tokens.css**（写入路径第 4 条之外）：按验收 1 的「1 个非主题族尺寸 token 或 1 条 allow」二选一授权，选 token，理由是它有 4 处消费点（MessageList ×3 + Composer ×1），比 4 条 allow 更省且可审计；未新增 allow。
4. **chips 边框用 `border: thin solid`**：token 集无边框宽度档，且本票 allow 不许增，故用关键字 `thin`（浏览器渲染 1px）替代 `1px` 字面量，沿用 T11 的先例。
5. **选中态渐变左边条消费 `--br-gradient-hero`**：README §1.5 的渐变点缀为四处（hero、综合分、类别徽章、会话选中态边条）；左边条取 hero 渐变的靛蓝档，宽度用 `--br-space-1`（4px）不新增尺寸 token。
6. **相对时间口径由执行方拟定**（刚刚 / N 分钟前 / N 小时前 / N 天前 / 7 天以上取日期前 10 位）：文案表未列该项；时钟在挂载时惰性读一次，避免每次渲染跳动，同时满足仓库 eslint 的 react-hooks/purity 与 set-state-in-effect。
7. **会话行次行未新增文案**：只有相对时间与既有消息数角标，没有新增「N 条消息」这类措辞。
8. **测试辅助改写 2 行**：fakeClient 签名新增 sessions 选项、listChatSessions stub 改为读该选项；两行都不是断言，既有断言零改（3.8 的 diff 核对）。
9. **新增 8 例单测**（票面最小集为 chips / 搜索 / 行动卡 ≥3 例）：另加 AppShell 通栏变体 2 例与相对时间纯函数 2 例；202 → 210。
10. **可选的日期分隔线未做**（票面标注可选）。
