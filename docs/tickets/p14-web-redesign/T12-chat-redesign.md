# P14-T12 — 对话页/首页改版 v2（通栏贴边 + 侧栏升级 + 空态 hero）

- Status: ready-for-agent
- Blocked by: 无
- 唯一写入路径：`apps/web/src/pages/ChatPage.tsx`、`ChatPage.module.css`、`ChatPage.test.tsx`；`apps/web/src/pages/chat/**`（SessionSidebar / MessageList / Composer.module.css / relativeTime.ts）；`apps/web/src/components/AppShell.tsx`、`AppShell.module.css`、`AppShell.test.tsx`（仅追加变体用例）；`apps/web/src/styles/tokens.css`（仅新增 `--br-width-measure`）；本票与 `T12-EVIDENCE.md`

> 依据 README §1.5 视觉语言；T7-EVIDENCE（聊天页现状与 composes 配方）；T10-EVIDENCE（交互态 token）；T3-EVIDENCE（AppShell 现状）；D24 / D25。
> 线框 v2 已经用户逐条批准：通栏贴边 / 侧栏搜索 / 文案用本包拟稿。
> 纪律：零新 API、零新业务逻辑、不引组件库、不改路由表与既有测试断言、不 commit。

## 目标

1. **通栏贴边**：对话页内容通栏——会话侧栏贴窗口左缘（宽 300px，保留页内二级栏语义与 <1024 顶部折叠），主区占余下宽度；主区内部消息列与 composer 可读宽度 860px 居中。机制：AppShell 内容容器新增通栏变体（`.contentFull`，对话页路由启用），不使用负边距 / 100vw 逃逸。顶栏结构、导航、用户区不动。
2. **侧栏升级**：顶部「＋ 新建对话」主按钮；本地搜索框（对已加载会话列表做大小写不敏感子串匹配，纯前端、零 API）；会话行 = 标题 + 末条消息预览一行 + 相对时间 + 选中态（渐变左边条 + accent-muted 弱底，用 T10 交互态 token）+ hover 删除（现有）；无结果时显示空结果文案。
   - 数据源约束（待确认）：会话列表 `ChatSessionView`（`apps/api/src/better_resume/chat/models.py:30-37`）没有末条消息预览字段，生成类型 `apps/web/src/api/schema.d.ts:483-504` 同；在零新 API 红线内，会话行次行落为相对时间，预览未落地。落地口径与偏差见 `T12-EVIDENCE.md` §五。
3. **空态主区**（无消息 / 无会话时）：hero 块 = 问候语 + 一行说明 + 6 个建议 chips（点击 = 把文案填入输入框，纯前端）+ 行动卡（标题 / 说明 / 按钮，跳 `/interview`，纯路由）；有消息时让位于消息列。
4. **主区头**：左侧会话标题（有会话时），右侧模型 Select（现状保留）。
5. 消息列 / composer 视觉配方不动；消息多时的日期分隔线为可选项，本票未做。

## 文案（用户已批准，照用）

- 问候语：今天想练点什么？
- 说明：直接提问，或从下面的建议开始；要整套流程就上传简历，进模拟面试。
- chips（6）：出一套项目深挖题 / 把一个技术取舍讲清楚 / 五道八股基础题带答案要点 / 准备 1 分钟自我介绍 / 实习深挖题练手 / 复盘一次失败经历怎么讲
- 行动卡：标题「上传简历，开始一轮模拟面试」；说明「AI 按简历出题、追问、评分，最后给报告」；按钮「去上传」
- 搜索框 placeholder：搜索会话；空结果文案：没有匹配的会话

## 红线

- 零新 API / 零新业务逻辑：chips 只填输入框、行动卡只跳路由、搜索只做本地过滤；不碰 `src/api`、`src/chat` 语义层（store / queries / selectors / useChatStream / useSession）、`src/stream`、`src/audio`；转写合并链零改动；Composer 的提交 / 禁用语义不动。
- 不动路由表、REST 契约、依赖、`package.json`；不引组件库。
- 不改既有测试断言（含 AppShell 导航高亮断言）；不动 README、T1–T11 票与既有 EVIDENCE。
- 不 commit。
- 数值锁定：侧栏 300px、可读宽 860px、断点 1024px。
- 搜索规则锁定：大小写不敏感子串，不做拼音 / 模糊 / 正则。
- 文案一字不改；token 只用现有集合 + 本票新增的 `--br-width-measure`（非主题族尺寸 token，用于可读宽度）；`allow:` 白名单维持 41 条不增。

## 验收

| 命令 | 期望 |
| --- | --- |
| `python3 scripts/check_web_style_guards.py` | exit 0，末行 `check_web_style_guards: ok` |
| `grep -rn 'allow:' apps/web/src \| wc -l` | 41（不增；可读宽度走 token，未新增 allow） |
| `pnpm -C apps/web test --run` | ≥205 passed（基线 202 + 新增 8，只增不减） |
| `pnpm -C apps/web typecheck`、`pnpm -C apps/web lint` | exit 0 |
| 变异证明 `bash scripts/verify_mutation.sh` | 删 chips 填入的状态更新 → 对应新单测红 → 恢复绿；sha256 / cmp 逐字节一致 |
| `bash scripts/verify.sh --layer all` | 末行 `ALL PASS (… commands)`，exit 0 |
| 通栏实证（浏览器量贴边） | 可选；无浏览器时记未验证 |

## 红-绿切片

1. chips 填入行为：点某 chip → 输入框值等于该文案（新测试，真红-绿）。
2. 侧栏搜索过滤：输入关键词 → 列表只剩匹配会话；清空恢复；无匹配显示空结果文案（新测试，真红-绿）。
3. 行动卡导航：点「去上传」→ navigate 到 `/interview`（新测试，真红-绿）。
4. AppShell 内容容器通栏变体：`/chat` 带 `.contentFull`、其他路由不带（追加变体行为用例，真红-绿）。
5. 相对时间纯函数：注入 now 的确定性单测（新测试）。
6. 既有 202 例保绿，断言零改。

## 不做

- 不做消息日期分隔线（可选项，未做）。
- 不做移动端精雕、不引视觉快照测试、不改守卫脚本与守卫测试、不改 `verify.sh`。
- 不改 `pages/chat/Composer.tsx` 与 `MessageBubble.*`：Composer 只在 CSS 上加可读宽度居中。
