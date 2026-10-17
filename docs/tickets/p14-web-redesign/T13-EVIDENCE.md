# P14-T13 验收包 — 报告页收尾小修：pending 等待态 / 回放组头去重 / 空态卡宽度

- 票据：docs/tickets/p14-web-redesign/T13-polish.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.4 报告页线框 / §1.5 视觉语言；T4-EVIDENCE.md；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

票据只做三件事，口径照票：

1. **报告 pending 态**：`report.summary_pending === true` 时「改进建议」卡显示等待态「总结生成中…」（Spinner + 文案，轻量一行）；只在 `summary` 为空且非 pending 时显示既有降级文案「未生成总结（模型不可用或未配置），分数与逐题记录不受影响。」——该文案一字未改。
2. **逐题回放组头去重**：组头由「第 N 题 · <题面>」改为「序号徽记（数字）+ 题面原文」；折叠开合与「全部展开 / 全部收起」语义不变。
3. **空态卡宽度**：`Empty` 内容宽度上限约 480px 并居中，字号层级微调；只调宽度与层级，不重设计。

不做（照票）：不动业务逻辑、数据流、TanStack Query / zustand 用法、REST 契约、路由表；不碰 `src/api`、`src/audio`、`src/stream`、`src/chat` 语义层；不新增依赖、不新增 token、不新增 `allow:` 白名单；不动 README、T1–T12 票与既有 EVIDENCE；不 commit。

## 二、实现决定交代

### 2.1 pending 等待态

- 判定顺序：`summaryPending`（= `reportQuery.data.summary_pending`）> `view.summary` 有值 > 降级文案。即 pending 为真、且 `summary` 已有值时仍显示等待态，符合「后端边写边返回」的口径。
- 等待态节点：`<p className={styles.summaryPending}>` 内 `<Spinner label="正在生成总结" />`（`role="status"`）＋ `<span>总结生成中…</span>`；`.summaryPending` 为一行 flex（gap `--br-space-2`、`--br-text-sm`、`--br-color-text-muted`）。
- 降级文案仍走原 `.note`，仅剩「非 pending 且 summary 空」一条分支。

### 2.2 组头去重

- `Collapsible` 的 `label` 传题面原文 `group.head.question`，不再拼 `"第 " + question_no + " 题 · "` 前缀。
- 序号徽记由 CSS 生成：`.turnGroups { counter-reset: turn-group; }` ＋ `.turnGroup { counter-increment: turn-group; }` ＋ `.turnGroup button::before { content: counter(turn-group); … }`；徽记样式与既有 `.suggestionNo` 同配方（`--br-space-5` 方块 / `--br-radius-pill` / `--br-color-accent-muted` 底 / `--br-color-accent` 字 / `--br-font-mono` / `--br-text-xs`）。
- 未改 `Collapsible`（其 `label` 只接受 `string`，且 `Collapsible.tsx` 不在本票写入路径）；折叠开合与「全部展开 / 全部收起」逻辑零改动。

### 2.3 空态卡

- 宽度：`.empty` 加 `width: 100%` ＋ `max-width: 30rem`（16px 根字号下 = 480px）＋ `margin-inline: auto` 居中；其余（虚线框、内边距、`--br-color-text-muted`、居中文本）不动。
- 字号层级：`.title` 由 `--br-text-md` 升到 `--br-text-lg` 并加 `--br-leading-tight`（与 `Card.module.css` 标题同档）；`.description` 保持 `--br-text-sm`、加 `--br-leading-normal`。
- token：全部取自既有集合，未新增 token、未新增 `allow:`。

### 2.4 组头断言改动逐条申报（4 例，均为文本 / 角色位置类）

`InterviewReportPage.test.tsx` 由 HEAD 的 11 例增到 13 例（+2 例 pending 行为），无删除。受组头文案影响改动的 4 例逐条如下（before → after，全部为「文本 / 角色位置」类）：

1. `replays every turn including the follow-up`
   - before：`expect(await screen.findByText("讲讲你的项目")).toBeInTheDocument();`
   - after：`const group = await screen.findByRole("region", { name: "讲讲你的项目" });` ＋ `expect(within(group).getByText("讲讲你的项目")).toBeInTheDocument();`
   - 理由：题面现同时出现在组头按钮与题面段两处，全局精确文本匹配会命中 2 处而抛 multiple elements；改为先按 `region` 角色名定位展开组、再在组内断言题面文本。断言意图（回放含该题面）与条数不变。

2. `opens only the first question group by default`
   - before：`findByRole("button", { name: "第 1 题 · 主问题一" })` / `getByRole("button", { name: "第 2 题 · 主问题二" })` / `getByText("主问题一")` / `queryByText("主问题二")`
   - after：`findByRole("button", { name: "主问题一" })` / `getByRole("button", { name: "主问题二" })` / `within(getByRole("region", { name: "主问题一" })).getByText("主问题一")` / `queryByRole("region", { name: "主问题二" })`
   - 理由：按钮可及名去掉「第 N 题 · 」前缀属文本类；折叠内容的存在性由「`region` 是否在树中」表达属角色位置类。

3. `toggles one question group from its header`
   - before：按钮名同前缀；`queryByText("主问题一")` / `getByText("主问题一")`
   - after：按钮名 `主问题一`；`queryByRole("region", { name: "主问题一" })` / `within(getByRole("region", { name: "主问题一" })).getByText("主问题一")`
   - 同上，文本 + 角色位置。

4. `expands and collapses every question group at once`
   - before：按钮名前缀；`getByText("主问题二")` / `queryByText("主问题二")`
   - after：按钮名 `主问题二`；`within(getByRole("region", { name: "主问题二" })).getByText("主问题二")` / `queryByRole("region", { name: "主问题二" })`
   - 同上，文本 + 角色位置。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（前端命令从仓库根跑）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
~~~

### 3.1 守卫与白名单

~~~bash
python3 scripts/check_web_style_guards.py; echo GUARD_EXIT=$?
grep -rn 'allow:' apps/web/src | wc -l
~~~

原始输出：

~~~text
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0
41
~~~

读数：守卫 exit 0；`allow:` 计数 41（未增，与票面一致）。

### 3.2 前端全量测试 / typecheck / lint

~~~bash
pnpm -C apps/web test --run
pnpm -C apps/web typecheck
pnpm -C apps/web lint
~~~

原始输出（尾部）：

~~~text
 Test Files  27 passed (27)
      Tests  215 passed (215)
TEST_EXIT=0

$ tsc --noEmit
TC_EXIT=0

$ eslint .
LINT_EXIT=0
~~~

读数：27 个测试文件、215 例全绿（基线约 213，只增不减）；typecheck exit 0；lint exit 0。

### 3.3 新增行为单测（2 例）

缝：README §4.1「带逻辑的新组件行为单测」。`InterviewReportPage.test.tsx` 新增：

~~~text
it("waits for the summary while it is still generating")
  fixture: { ...REPORT, summary: null, summary_pending: true }
  断言：findByText("总结生成中…") 在；queryByText(/未生成总结（模型不可用或未配置）/) 不在。

it("keeps the degraded summary copy when nothing is pending")
  fixture: { ...REPORT, summary: null, summary_pending: false }
  断言：findByText(/未生成总结（模型不可用或未配置）/) 在；queryByText("总结生成中…") 不在。
~~~

单文件实测：`pnpm -C apps/web test --run src/pages/InterviewReportPage.test.tsx` → `Tests 13 passed (13)`，exit 0。

### 3.4 变异证明 ×1（删 pending 判定）

~~~bash
bash scripts/verify_mutation.sh --test "cd '/root/better resume' && pnpm -C apps/web test --run src/pages/InterviewReportPage.test.tsx" --file "/root/better resume/apps/web/src/pages/InterviewReportPage.tsx" --find "{summaryPending ? (" --replace "{false ? ("
~~~

原始输出（关键行）：

~~~text
== 1/3 baseline: the test must PASS on the untouched implementation ==
 ✓ src/pages/InterviewReportPage.test.tsx (13 tests) 429ms
      Tests  13 passed (13)

== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/pages/InterviewReportPage.tsx ==
mutated 1 occurrence in /root/better resume/apps/web/src/pages/InterviewReportPage.tsx

== 2/3 red: the test must FAIL on the mutated implementation ==
 × waits for the summary while it is still generating 1009ms
      Tests  1 failed | 12 passed (13)
TestingLibraryElementError: Unable to find an element with the text: 总结生成中….
ok: mutation was caught

== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/pages/InterviewReportPage.tsx sha256=c1526ddf4453eb32…
      Tests  13 passed (13)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/InterviewReportPage.tsx)
~~~

sha / cmp 复核（脚本内建 sha256 比对，另在脚本外再取一次）：

~~~text
变异前：c1526ddf4453eb325486c047548681ab4fa4e910178feaee2defaac674999c55  apps/web/src/pages/InterviewReportPage.tsx
变异后：c1526ddf4453eb325486c047548681ab4fa4e910178feaee2defaac674999c55  apps/web/src/pages/InterviewReportPage.tsx
MUT_EXIT=0
~~~

读数：删 pending 判定（`{summaryPending ? (` → `{false ? (`）→ 只红「waits for the summary while it is still generating」1 例 → 恢复后 13 例绿；文件 sha256 前后一致。

### 3.5 改动面自查

`git status --porcelain` 原文（工作区同时存在 T11 / T12 并行路的改动与产物，非本票写入面）：

~~~text
 M apps/web/src/components/AppShell.module.css
 M apps/web/src/components/AppShell.test.tsx
 M apps/web/src/components/AppShell.tsx
 M apps/web/src/components/Empty.module.css
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/ChatPage.test.tsx
 M apps/web/src/pages/ChatPage.tsx
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewReportPage.test.tsx
 M apps/web/src/pages/InterviewReportPage.tsx
 M apps/web/src/pages/LoginGate.module.css
 M apps/web/src/pages/LoginGate.tsx
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/MessageList.module.css
 M apps/web/src/pages/chat/MessageList.tsx
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/chat/SessionSidebar.tsx
 M apps/web/src/styles/tokens.css
 M docs/tickets/p14-web-redesign/README.md
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
?? docs/tickets/p14-web-redesign/T12-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T12-chat-redesign.md
?? docs/tickets/p14-web-redesign/T13-polish.md
?? docs/tickets/p14-web-redesign/T13-EVIDENCE.md
~~~

本票写入面的 `git diff --numstat` 原文：

~~~text
7	1	apps/web/src/components/Empty.module.css
30	0	apps/web/src/pages/InterviewReportPage.module.css
39	14	apps/web/src/pages/InterviewReportPage.test.tsx
30	22	apps/web/src/pages/InterviewReportPage.tsx
~~~

本票只落在写入路径内：`InterviewReportPage.tsx` / `.module.css` / `.test.tsx` / `Empty.module.css`；`Empty.tsx` 未改（0 行）；其余 `git status` 里的文件属 T11 / T12 并行路（AppShell / ChatPage / LoginGate / chat/* / tokens.css / README / docs/design/*），本票未触碰。

## 四、未验证项诚实清单

1. **浏览器视觉未实测**：空态卡在 5 个调用点（`InterviewIntroPage` ×1、`InterviewRoomPage` ×2、`chat/MessageList`、`InterviewReportPage`）的实际宽度与居中、组头序号徽记的实际渲染，均未在浏览器查看；jsdom 不计算 CSS counter，守卫只查 token / 裸值，不等价于视觉验收。
2. **序号徽记的可达性未验证**：徽记是 `::before` 生成内容，不在 DOM 文本与无障碍树中；屏幕阅读器是否读出未验证。逐题卡内仍有 `aria-label="回放题号 N"`（未改）。
3. **rem 随根字号缩放**：`30rem` 在 16px 根字号下 = 480px；非 16px 根字号下的实际宽度未验证。
4. **窄屏未实测**：容器宽度 < 480px 时 `width:100% + max-width` 语义上不会溢出，但未在浏览器实测。
5. **pending 单测的「实现前红相」未由本轮观测**：交接面上该实现与单测已同时存在并绿；红-绿由 §3.4 变异证明承担。组头 4 例的断言改动同理，未单独在旧实现上演示红相。
6. **`bash scripts/verify.sh --layer all` 与 apps/api pytest 未跑**：按并发安全约定（三路并行）由主代理收口统一跑。
7. **空态卡纯样式无新单测**（票据口径）；既有 `components.test.tsx` 的 Empty 1 例仍在全量 215 例内且绿。

## 五、与提案的偏差

1. **空态宽度用 `max-width: 30rem` 表达 480px，而非「token 内取值」**：token 集只有 `--br-width-content`(1200px) / `--br-width-measure`(860px) 两档，无 ~480px 档；新增 token 与新增 `allow:` 都超出本票（且验收要求 `allow:` 计数 41 不增）。`rem` 是守卫 G2（裸 hex/px/rgb/hsl）之外的版式单位，与既有先例 `apps/web/src/pages/LoginGate.module.css:39`（`max-width: 26rem`）一致。（已经用户确认，2026-10-13）
2. **组头序号用 CSS counter 生成，不是 DOM 文本**：`Collapsible` 的 `label` 只接受 `string`，且 `Collapsible.tsx` 不在本票写入路径。视觉满足「序号徽记（数字）+ 题面原文」，但序号对无障碍树不可见。（已经用户确认，2026-10-13；逐题卡 `aria-label` 为兜底）
3. **字号层级落点**：`.title` 由 16px（`--br-text-md`）升到 20px（`--br-text-lg`），是票面「字号层级微调」的落地口径（20px 已经用户确认，2026-10-13）。

未改业务逻辑 / 数据流 / REST 契约 / 路由 / 数据层；未碰 `src/api`、`src/audio`、`src/stream`、`src/chat` 语义层；未新增依赖、token、`allow:`；未 commit。