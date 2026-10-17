# P14-T11 验收包 — 登录门 hero 化（补漏票）

- 票据：docs/tickets/p14-web-redesign/T11-login-gate.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.4「登录门（首屏）」线框 / §1.5 / §4.1 / §4.3；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

README §1.4「登录门」一块在页面批无承接票（规划侧漏拆），用户裁定补做；线框七块已逐块确认，本票即该块的施工规格。只做三件事：

1. **全屏门面**：门面居中呈现，渐变底衬与通栏由 AppShell 登录门变体承载（覆盖含顶栏的整个视口）；底色用既有 token 组合 `--br-color-accent-muted → --br-color-bg`，不新增渐变 token。
2. **居中 hero**：大字阶产品名 `better-resume`（`--br-text-hero`，42px，`--br-gradient-hero` 渐变文字）＋ 一句话价值主张。
3. **玻璃质感登录卡**：半透明表面 ＋ 发丝边框 ＋ `--br-shadow-md` 柔阴影；卡内为用户名输入（`Input`，等价替换原 `Textarea rows=1`）＋「进入」按钮。

不做：不改登录行为语义、不动业务逻辑/数据流/路由/REST、不碰 `components/` 与 `styles/`、不改守卫脚本/测试/`verify.sh`、不改既有测试断言、不新增依赖、不新增 allow、不新增 token、不新增单测（无新可观察行为）、不 commit、不截图。

## 二、实现决定交代

### 2.1 线框落地结构

- `.gate`：纵向 flex、`min-height: 100%`、居中；`padding` 用 `--br-space-7 / --br-space-6`。横向通栏由 AppShell 登录门变体的 `.contentGate`（`max-width: none; margin: 0;`）承担，门面自身不做全出血。
- `.hero`：`header`，`h1` 产品名 ＋ `p` 价值主张。
- `.card`：`section`（不再用 `Card` 组件，理由见 §五）；卡内 `.cardSurface` 为独立表面层（`span aria-hidden`），`.cardBody` 承载正文。

### 2.2 渐变与 token

- 背景渐变 = `linear-gradient(180deg, var(--br-color-accent-muted) 0%, var(--br-color-bg) 62%)`，由 AppShell 登录门变体的 `.shellGate` 承载，覆盖含顶栏的整个视口（`.topbarGate` 让顶栏透明叠在渐变上）；由既有 token 组合出的低饱和靛蓝渐隐，深浅色随 token 自动适配。**未新增 token**（AppShell 与门面引用的 token 全为既有集合，见 §3.4 清单）。
- 产品名渐变文字 = `--br-gradient-hero`（T2 引入、已深浅双定义），与 README §1.5「渐变只做点缀（hero、综合分、类别徽章、会话选中态边条）」的口径一致。
- 字阶用 `--br-text-hero`（42px），沿用 T10 落地的 hero 档。

### 2.3 玻璃质感的实现取舍

- **半透明表面**：独立表面层 `.cardSurface` 用 `background: var(--br-color-surface-raised)` ＋ `opacity: 0.82`，让表面与背后渐变叠加；文字层 `.cardBody` 不透明，不受影响。未用 `rgba()`/`color-mix()`/`backdrop-filter`，不引新技术依赖、不写裸色值、不新增 token。
- **发丝边框**：`border: thin solid var(--br-color-border)`。token 集内没有边框宽度档，`border-width` 关键字 `thin` 在浏览器里渲染为 1px；这样在不写裸 px 的前提下保持 `allow:` 白名单 41 条不增（新增 allow 需先停下报，本票未新增）。
- **柔阴影**：`box-shadow: var(--br-shadow-md)`（浮层级）。
- 未新增 animation / transition：门面无新动效，Button / Input 的 hover / active / focus 与 reduced-motion 覆盖沿用 T10 落地的组件样式，守卫④维持绿。

### 2.4 价值主张文案（原文列出，待用户拍板）

> 上传简历，AI 出题、追问、评分，把面试练到能上场。

该句由执行方拟定（票据授权），落在 `LoginGate.tsx` 的 `.tagline`；既有功能文案——提示「还没有正式登录（M2 上线账号体系）。这里输入任意用户名即可创建本地会话。」、错误「登录失败：…」、`aria-label="用户名"`、按钮「进入」——一字符未改。

### 2.5 行为等价与键盘可达

- `login.mutate(userId.trim() || "demo")`、`login.isPending` → `loading`、`role="alert"` 错误、`useState` 受控 value/onChange 全部原样；仅把输入元素由 `Textarea rows=1` 换成样式化 `Input`（票据明确允许的等价替换），未包 form、未加 Enter 提交。
- 键盘可达：输入与按钮都是原生可聚焦元素，Tab 顺序（输入 → 按钮）与既有语义一致；Enter 在输入框不触发登录（无 form），与改前「Enter 不提交」一致。
- 可观察差异只有一项：`Textarea` 的「Enter 插入换行」不再发生；`userId.trim()` 使该差异不影响登录结果，属票据许可的等价替换范围（§五 记为偏差）。

### 2.6 无新单测与红-绿落点

本票没有新可观察行为（输入控件是等价替换、其余是纯样式），按 README §4.1「纯样式不写测试」不新建 `LoginGate.test.tsx`，也没有能先在旧代码上演示红的用例；红-绿由守卫变异承担（§3.5）。

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
41
~~~

数字：退出码 0；扫描 27 个 .css；违规 0；末行 ok；`allow:` 白名单 41 条，与本票改前基线逐字相同、新增 0（本票零几何放行）。

### 3.2 既有登录门断言零改动

~~~text
$ git diff --numstat -- apps/web/src/pages/ChatPage.test.tsx apps/web/src/pages/InterviewIntroPage.test.tsx
（空输出）
PROTECTED_DIFF_LINES=0
~~~

数字：两个受保护测试文件 diff 0 行。其登录门断言（`ChatPage.test.tsx:125-130`、`InterviewIntroPage.test.tsx:74-82`，均 `findByRole("button", { name: "进入" })`）在 §3.3 的 202 例全绿中通过。

### 3.3 前端测试 / typecheck / lint

~~~text
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  202 passed (202)
VITEST_EXIT=0

$ pnpm -C apps/web typecheck
$ tsc --noEmit
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
~~~

数字：26 文件 / 202 例全绿。改前基线同为 26 / 202（本票未增删测试，只增不减）；typecheck 与 lint 退出码 0。

### 3.4 登录门 token 引用清单（全部为既有 token）

~~~text
$ grep -on -- '--br-[A-Za-z0-9_-]*' apps/web/src/pages/LoginGate.module.css | cut -d: -f2 | sort -u
--br-color-border
--br-color-danger
--br-color-surface-raised
--br-color-text-muted
--br-gradient-hero
--br-leading-tight
--br-radius-lg
--br-shadow-md
--br-space-3
--br-space-4
--br-space-6
--br-space-7
--br-text-hero
--br-text-md
--br-text-sm
~~~

数字：`LoginGate.module.css` 15 个引用全部在 `styles/tokens.css` 有定义；`--br-color-accent-muted` 与 `--br-color-bg` 归 AppShell 登录门变体（`.shellGate`）消费；新增 token 0 个；无 `var(--br-*, 兜底)` 形式。

### 3.5 变异证明（删/改 hero 渐变消费 → 守卫①红 → 恢复绿）

锚点是本票新增的 hero 渐变消费行，属真变异：消费引用的 token 变成未定义，守卫①必须点名它。

~~~text
$ sha_before=$(sha256sum '/root/better resume/apps/web/src/pages/LoginGate.module.css' | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh --test 'python3 scripts/check_web_style_guards.py' \
    --file '/root/better resume/apps/web/src/pages/LoginGate.module.css' \
    --find 'background: var(--br-gradient-hero);' --replace 'background: var(--br-gradient-gate-hero);'; echo MUT_EXIT=$?
== 1/3 baseline: the test must PASS on the untouched implementation ==
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)

== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/pages/LoginGate.module.css ==
mutated 1 occurrence in /root/better resume/apps/web/src/pages/LoginGate.module.css

== 2/3 red: the test must FAIL on the mutated implementation ==
pages/LoginGate.module.css:24: G1 --br-gradient-gate-hero 被引用但没有定义（守卫① token 零假变量）
check_web_style_guards: 1 violation(s)
ok: mutation was caught

== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/pages/LoginGate.module.css sha256=6151280c7c5a034e…
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)

PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/LoginGate.module.css)
note: /root/better resume/apps/web/src/pages/LoginGate.module.css still differs from HEAD (pre-existing changes are intact)
MUT_EXIT=0
sha_before=6151280c7c5a034e1fc28d33c7ade4ffc27a122222c99abf4a92d0757ef30ccb
sha_after=6151280c7c5a034e1fc28d33c7ade4ffc27a122222c99abf4a92d0757ef30ccb
CMP_OK
~~~

数字：基线绿 → 变异红（G1 点名 `pages/LoginGate.module.css:24`）→ 恢复绿；恢复后 sha256 与变异前同为 `6151280c7c5a034e…`，`cmp` 逐字节相同；`--file` 用绝对路径。

### 3.6 verify --layer all

~~~text
$ bash scripts/verify.sh --layer all
[1/17] cd apps/api && uv run pytest --cov=... → 997 passed, 3 warnings in 92.27s（TOTAL 6553 stmts / 305 miss / 95%）
[2/17] check_coverage_floors.py → floors ok
[3/17] pnpm -C apps/web exec vitest run → 26 passed (26) / 202 passed (202)
[4/17] cd apps/api && uv run ruff check . → All checks passed!
[5/17] cd apps/api && uv run ruff format --check . → 268 files already formatted
[6/17] alembic upgrade head → ok
[7/17] alembic check → No new upgrade operations detected.
[8/17] export_openapi.py --check → openapi.json is up to date
[9/17] extract_api_index.py --check → API index is up to date
[10/17] pnpm -C apps/web lint → exit 0
[11/17] pnpm -C apps/web typecheck → exit 0
[12/17] pnpm -C apps/web check:api → src/api/schema.d.ts 无 diff
[13/17] python3 scripts/check_web_style_guards.py → ok (27 css file(s))
[14/17] pytest tests/test_fault_probe.py ... → 101 passed, 2 warnings in 7.51s
[15/17] for f in scripts/*.sh; do bash -n "$f"; done → shell syntax ok
[16/17] check_scripts.py → script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[17/17] verify_audit_evidence.py --structural → structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T132903Z-all
VERIFY_ALL_EXIT=0
~~~

数字：17 条命令全过，末行 ALL PASS，退出码 0；API 997 passed；coverage floors 过（TOTAL 95%）；web 202 passed；契约三件套零 diff；守卫绿。

### 3.7 改动面自查

~~~text
$ git status --porcelain
 M apps/web/src/pages/LoginGate.module.css
 M apps/web/src/pages/LoginGate.tsx
?? docs/tickets/p14-web-redesign/T11-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T11-login-gate.md

$ git diff --numstat
57	1	apps/web/src/pages/LoginGate.module.css
34	30	apps/web/src/pages/LoginGate.tsx
~~~

逐文件说明：

- `apps/web/src/pages/LoginGate.module.css`（+53 −1）：本票唯一实质改写文件；登录门布局（渐变底衬与通栏由 AppShell 登录门变体承载）、hero（`h1` 渐变文字 + 价值主张）、玻璃卡（表面层 `opacity`、`thin` 边框、柔阴影）。
- `apps/web/src/pages/LoginGate.tsx`（+34 −30）：结构改 hero + 玻璃卡；输入由 `Textarea rows=1` 换 `Input`、`Card` 换成自持 `section`；登录行为代码逐字未动。
- `docs/tickets/p14-web-redesign/T11-login-gate.md`、`T11-EVIDENCE.md`（新建，未跟踪）：本票与验收包。

未触碰：`apps/web/src/pages/ChatPage.test.tsx`、`InterviewIntroPage.test.tsx`、`components/`、`styles/`、`src/api`、`src/audio`、`src/stream`、`src/chat`、`scripts/`、`README.md`、T1–T10 票与 T1–T10-EVIDENCE；无新依赖；无 commit。

## 四、未验证项诚实清单

- 浏览器视觉观感未验证：低饱和靛蓝渐变的实际观感、玻璃表面 82% 透明度、渐变文字的渲染色带、渐变含顶栏铺满与顶栏透明叠层的观感，AI 无浏览器与截图能力，一处都未人工核验（截图按 `docs/design/SHOT-LIST.md` 由用户手拍）。
- 深色主题未人工核对：渐变两端、半透明表面与发丝边框在 `prefers-color-scheme: dark` 下的观感只有 token 静态定义保证，未实机切换。
- `border-width: thin` 渲染为 1px 未在浏览器实测；依据是 CSS 关键字语义与主流实现默认值，属「未实测」。
- `max-width: 26rem` 的卡片宽度是执行方取值，未做多分辨率核对；`100%` 内容区与 hero 的居中关系未人工核验。
- 键盘可达（Tab 顺序、Enter 不提交、focus 环可见）未人工手测；只有静态结构保证 + 既有页面测试确认「进入」按钮可被无障碍角色查询到。
- 「全屏」作用域由 AppShell 登录门变体决定（`.shellGate` 渐变底衬 ＋ `.topbarGate` 透明顶栏 ＋ `.contentGate` 通栏，见 §五 1）；渐变覆盖含顶栏的整个视口，顶栏透明叠层后的观感未人工核验。
- 未跑 `bash scripts/compose_smoke.sh`，未核对 nginx 缓存头与 bundle hash（本票未改部署面与构建产物）。
- MANUAL-TESTING §1.1–1.4 的实时转写 / 答题交互未手测；本票未触碰相关路径。
- 无视觉快照测试（本阶段明确不引）；jsdom 不应用伪类与媒体查询，玻璃与渐变只有静态存在性检查。

## 五、与提案的偏差

1. **「全屏」作用域：渐变覆盖含顶栏的整个视口**：底衬渐变由 AppShell 的登录门变体承载——登录门路由（`/chat`、`/interview`）未登录时给页壳加 `shellGate`（渐变底衬）、顶栏加 `topbarGate`（透明叠在渐变上，产品名/导航/用户区结构与语义不变）、内容加 `contentGate`（通栏）；登录门自身不着色、不做横向全出血。
2. **玻璃表面用独立层 `opacity`，未用 `rgba()` / `color-mix()` / `backdrop-filter`**：`rgba()` 是守卫②的裸值、`color-mix()` 属票据「不许引 backdrop-filter 之外的新技术依赖」的灰区，`opacity` 方案零新增 token、零新增 allow、零新技术，代价是多一个装饰层 `span`。未使用 `backdrop-filter`，故无该兼容性未验证项。
3. **发丝边框用关键字 `thin`**：token 集无边框宽度档，票据要求 allow 不增，故用 `border-width: thin`（浏览器渲染 1px）替代 `1px` 字面量；白名单保持 41 条。
4. **卡片标题去留**：原 `Card title="进入 better-resume"` 的 `h2` 由 hero 的 `h1` 承接后移除（否则与大字产品名重复）；提示/错误/`aria-label`/按钮文案未动。此项若判为「文案语义变更」，请指出，可改为视觉隐藏标题。
5. **价值主张文案由执行方拟定**（§2.4 原文），待用户拍板；如需替换只改 `LoginGate.tsx` 一行。
6. **未新增单测**：无新可观察行为、无法先红后绿，按 README §4.1 纯样式不写测试；红-绿由守卫变异承担（§3.5）。
7. **输入控件等价替换的可观察残留差异**：`Textarea` 的「Enter 插入换行」在 `Input` 上不再发生；`userId.trim() || "demo"` 使该差异不影响登录结果（§2.5），票据明确允许换 `Input`。
