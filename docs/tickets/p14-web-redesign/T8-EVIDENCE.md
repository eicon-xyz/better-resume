# P14-T8 验收包 — 设置页（token 重修 + 表格样式化 + 保存反馈）

- 票据：docs/tickets/p14-web-redesign/T8-settings-page.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.4 设置页线框（用户逐块确认）/ §1.5 视觉语言；D24 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

本票只做设置页一页的三件事，不动业务：

1. **保存状态反馈**：保存按钮在请求进行中显示「保存中」，成功后在该行给出「已保存」提示（失败提示沿用既有 role=alert 文案）。
2. **状态徽章**：表格状态列由裸 span 改为样式化 Badge，已配置=success、未配置=warning。
3. **token 重修**：清掉本页唯一一条 allow 白名单（960px 页宽裸值），改用既有 token；输入控件沿用样式化 Input / Select / Table。

不改场景绑定字段语义与请求体（adapter / target_ref / configured）、不改 CREDENTIAL_HINTS 文案语义、不改 REST 契约与路由；纯样式不写测试，行为测试只写票面点名的「保存生命周期」缝。

## 二、实现决定交代

### 2.1 保存生命周期（切片 2）

- 进行中：沿用既有 `saveMutation.isPending && variables?.scene === scene.scene` 判定，抽出局部变量 `saving`；按钮 `loading={saving}`（既有 Button 的 loading 会给 disabled + aria-busy），文案由「保存」切为「保存中」。Button 的 loading 只提供 busy/禁用态，不提供文案，票面要求「保存中」可见反馈，故文案由本页给。
- 成功：新增 `savedScene` 状态，`onSuccess` 里 `setSavedScene(variables.scene)`；该行操作列渲染 `<span role="status">已保存</span>`（role=status 即 aria-live 礼貌播报，供读屏与测试共同取用）。
- 再次编辑该页任意一行时 `setSavedScene(null)`，提示消失（避免「已保存」停留在已有未保存改动的行上）；失败不动 savedScene（此时本就为 null），错误仍走既有 alert。
- 只显示最近一次成功保存的那一行；同一时刻最多一条「已保存」。
- 数据流未变：`mutationFn` 仍调 `api.updateScene(scene, { adapter, target_ref })`，成功仍 `invalidateQueries(sceneKeys.list())`；新增的只是一个 React 展示状态。

### 2.2 状态徽章

- `styles.ok` / `styles.missing` 两个 span 换成 `<Badge tone="success">已配置</Badge>` / `<Badge tone="warning">未配置（检查环境变量）{CREDENTIAL_HINTS[...]}</Badge>`；两档 tone 消费既有 `--br-color-success` / `--br-color-warning` + `--br-color-warning-bg`。
- 未配置徽章仍把凭据提示文案放在同一个元素内，保持既有测试对「未配置」元素文本内容的断言（findByText(/未配置/) → toHaveTextContent("XINGCHEN_API_KEY")）原样成立，未改断言。
- CREDENTIAL_HINTS 三条文案与回退值一字未动。

### 2.3 token 重修与 allow 白名单

- 删除 `.page` 的 `max-width: 960px` + `margin: 0 auto` 及其上一行 allow：页宽改由 AppShell 内容容器（`--br-width-content` = 1200）统一约束，与其他页面一致。本页 allow 由 1 条降为 0 条，全站白名单 47 → 46（条数不增）。
- `.hint` 的 `line-height: 1.6` 改 `var(--br-leading-normal)`（1.65）；`.loading` 补 `color: var(--br-color-text-muted)`。两处都是既有 token，未新增 token、未新增 allow。
- 新增 `.actions`（操作列 flex 右对齐）与 `.saved`（成功提示色，`--br-color-success`）；无裸 hex/px，无 animation / transition（故无需 reduced-motion 重访）。

### 2.4 表格样式

- 表头弱化与数据行 hover 在 T3/T10 已落在 `components/Table.module.css`（表头 muted、行 hover surface-raised、hover 过渡 120ms + reduced-motion 覆盖），本页直接用 `<Table>` 承接，未改组件；本页未新增任何动效。

### 2.5 红线自查

- 未新增依赖、未引 webfont/动效库；未碰 apps/web/src/api、src/audio、src/stream、components/、styles/、守卫脚本/守卫测试/verify.sh/README、T1–T10 票与既有 EVIDENCE。
- 本页控件全部为既有样式化组件（Table / Select / Input / Button / Badge / Card），守卫⑤绿。
- 未改任何既有测试断言；新增 1 例行为单测，全量例数 186 → 187。

## 三、可复跑命令 + 原始输出 + 数字

环境（每条命令前执行，前端命令从仓库根跑）：

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
```

### 3.1 先红（切片 2 的新行为单测，实现尚未改）

```text
$ pnpm -C apps/web exec vitest run src/pages/AiSettingsPage.test.tsx
 ❯ src/pages/AiSettingsPage.test.tsx:191:44
    189|     fireEvent.click(saveButton);
    190|
    191|     await waitFor(() => expect(saveButton).toHaveTextContent("保存中"));
       |                                            ^

 Test Files  1 failed (1)
      Tests  1 failed | 8 passed (9)
EXIT=1
```

数字：新增用例 1 例红；既有 8 例仍绿（失败点在「保存中」文案，未实现前不出现）。

### 3.2 后绿 + 全量

```text
$ pnpm -C apps/web exec vitest run src/pages/AiSettingsPage.test.tsx
 ✓ src/pages/AiSettingsPage.test.tsx (9 tests) 376ms
 Test Files  1 passed (1)
      Tests  9 passed (9)
VITEST_EXIT=0

$ pnpm -C apps/web test --run
      Tests  187 passed (187)
VITEST_EXIT=0
```

数字：本文件 9 例全绿；全量 26 文件 / **187 passed**（基线 186，只增 1，未删未改既有断言）。

本票行为单测清单（1 例）：

- `AiSettingsPage > reports the save lifecycle: busy while in flight, confirmed once stored`
  - 保存中：点击保存（updateScene 挂在一个受控 Promise 上）→ 按钮文案变「保存中」、`aria-busy="true"`、此时页面上没有 role=status。
  - 已保存：resolve 该请求 → 出现 `role="status"` 且文本为「已保存」，按钮 aria-busy 移除。
  - 断言只走公开可见行为（按钮文案 / aria-busy / role=status + 文本），不引入测试专用属性。

### 3.3 守卫②与白名单

```text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
GUARD_EXIT=0

$ grep -rn 'allow:' apps/web/src | wc -l
46
$ grep -rn 'allow:' apps/web/src/pages/AiSettingsPage.module.css
(无输出)
```

数字：守卫①–⑤ 全部退出码 0、末行 ok、扫描 27 个 .css；白名单 47 → **46**（本页唯一一条 allow 被 token 化的页宽替代，无新增）。

### 3.4 typecheck / lint

```text
$ pnpm -C apps/web typecheck
$ tsc --noEmit
TYPECHECK_EXIT=0

$ pnpm -C apps/web lint
$ eslint .
LINT_EXIT=0
```

数字：两项退出码均 0，无告警输出。

### 3.5 变异证明（真变异：删掉成功状态记录）

锚点取 `onSuccess` 里唯一一行 `setSavedScene(variables.scene);`——删掉它「已保存」不再出现，而保存请求本身照发，是本票新增反馈行为的真锚点。

```text
$ TMP=$(mktemp -d); cp -- 'apps/web/src/pages/AiSettingsPage.tsx' "$TMP/before.tsx"
$ sha_before=$(sha256sum 'apps/web/src/pages/AiSettingsPage.tsx' | cut -d' ' -f1)
$ bash scripts/verify_mutation.sh \
    --test 'pnpm -C apps/web exec vitest run src/pages/AiSettingsPage.test.tsx' \
    --file '/root/better resume/apps/web/src/pages/AiSettingsPage.tsx' \
    --find 'setSavedScene(variables.scene);' --replace ''; echo MUT_EXIT=$?
== 1/3 baseline: the test must PASS on the untouched implementation ==
 ✓ src/pages/AiSettingsPage.test.tsx (9 tests)
      Tests  9 passed (9)
== 2/3 mutate: apply --find/--replace to /root/better resume/apps/web/src/pages/AiSettingsPage.tsx ==
mutated 1 occurrence in /root/better resume/apps/web/src/pages/AiSettingsPage.tsx
== 2/3 red: the test must FAIL on the mutated implementation ==
 ❯ src/pages/AiSettingsPage.test.tsx (9 tests | 1 failed)
     × reports the save lifecycle: busy while in flight, confirmed once stored
TestingLibraryElementError: Unable to find role="status"
     Tests  1 failed | 8 passed (9)
ok: mutation was caught
== 3/3 restore: the test must PASS again ==
restored: /root/better resume/apps/web/src/pages/AiSettingsPage.tsx sha256=4825248085852d7a…
      Tests  9 passed (9)
PASS: baseline green -> mutation red -> restored green (/root/better resume/apps/web/src/pages/AiSettingsPage.tsx)
note: /root/better resume/apps/web/src/pages/AiSettingsPage.tsx still differs from HEAD (pre-existing changes are intact)
MUT_EXIT=0

$ sha_after=$(sha256sum 'apps/web/src/pages/AiSettingsPage.tsx' | cut -d' ' -f1)
sha_before=4825248085852d7a50061cde678c4e890488b2add9e63bfd88f4dc945647875a
sha_after=4825248085852d7a50061cde678c4e890488b2add9e63bfd88f4dc945647875a
$ cmp "$TMP/before.tsx" 'apps/web/src/pages/AiSettingsPage.tsx' && echo CMP_OK
CMP_OK
```

数字：基线绿 → 变异红（`Unable to find role="status"`，其余 8 例仍绿）→ 恢复绿；恢复后 sha256 与变异前逐字节相同（`4825248085852d7a…`），`cmp` 通过；`--file` 用绝对路径。

### 3.6 改动面自查

```text
$ git status --porcelain
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/AiSettingsPage.test.tsx
 M apps/web/src/pages/AiSettingsPage.tsx
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md

$ git diff --numstat
12	8	apps/web/src/pages/AiSettingsPage.module.css
28	0	apps/web/src/pages/AiSettingsPage.test.tsx
38	25	apps/web/src/pages/AiSettingsPage.tsx
```

逐文件说明：

- `apps/web/src/pages/AiSettingsPage.tsx`（+38 −25）：import 加 Badge；新增 `savedScene` 状态；`onSuccess` 记录成功场景；行内抽出 `saving` / `saved`；两个 onChange 加清提示；状态列换 Badge；操作列包 `.actions`，加 `role=status` 的「已保存」提示，按钮文案随 `saving` 切「保存中 / 保存」。请求体与查询键零改动。
- `apps/web/src/pages/AiSettingsPage.module.css`（+12 −8）：删页宽 allow/max-width/margin；hint 行高走 token；删 `.ok` / `.missing`（已无消费点）；新增 `.actions` / `.saved`；`.loading` 补色。
- `apps/web/src/pages/AiSettingsPage.test.tsx`（+28 −0）：追加 1 例保存生命周期单测；既有 8 例一字未改。
- `docs/tickets/p14-web-redesign/T8-EVIDENCE.md`（新建，未跟踪）：本验收包。

## 四、未验证项诚实清单

- 浏览器视觉与手感未验证：徽章在表格窄列下的换行表现、操作列右对齐与「已保存」提示出现/消失的观感、页宽由 960 → 容器宽（≤1200）后的实际排布，AI 无浏览器与截图能力（截图按票据口径留给 T9 统一收口）。
- 深色主题下 Badge 的 warning/success 语义色与「已保存」文字对比度未人工核对；仅由守卫①静态保证深色成对定义。
- 保存反馈基于假客户端（受控 Promise）验证；未对真实后端做一次成功/失败切换的手测，`invalidateQueries` 后真实刷新时序未核。
- 窄屏（<1024）下本页表格与操作列的塌缩表现未核（本票未加断点，也不做移动端精雕）。
- 未跑 `bash scripts/verify.sh --layer all` 与 apps/api 的 pytest/uv（本波 4 张票并行，按派活口径避免互踩 coverage-api.json，由主代理统一收口）；未跑 `bash scripts/compose_smoke.sh`（本票不改部署面与构建产物）。
- 页面可点行的 hover/active 等人工交互项未复验（T10 范围，且本票未改动效）。
- 全量读数口径：§3.2 的 187 passed 取自工作区只有本票三个文件改动、HEAD=1047bd1 的时刻；本波其余页面票并行写入（如 InterviewIntroPage.test.tsx）后，树级全量会出现它们各自的红，与本票无关——本票文件单跑 9/9 绿。

## 五、与提案的偏差

1. 删除设置页 `.page` 的 `max-width: 960px`（含其 allow），把页宽交给 README §1.4 页壳的居中内容容器（`--br-width-content`，1200）。线框未写设置页自身宽度，本页原来是唯一一处页面级宽度上限；取「与其他页一致、清掉本页唯一裸值」的保守做法。若要求设置页单独窄排，请点名目标宽度并需要新 token 或保留 allow。
2. 保存反馈除「已保存」提示外，还把保存按钮文案在请求进行中切为「保存中」。既有 Button 的 loading 只给禁用 + aria-busy，没有可见文案；票面写「保存中/已保存」，故文案由本页给（不新增组件能力、不改 Button）。
3. 「已保存」提示在再次编辑任意一行时清除，且只保留最近一次成功保存的那一行；这是线框未规定的交互细节，取「提示不早于真实状态」的保守口径。
4. 未配置徽章把凭据提示文案放进同一个 Badge 元素内（而非「徽章=未配置」+ 另一行提示），以便既有测试对文本内容的断言一字不改地继续成立。
5. `.hint` 行高由裸 1.6 改为 `--br-leading-normal`（1.65），属 token 化的极小视觉位移。
6. 白名单由 47 降为 46（删本页 960px 一条），未新增任何 allow。
