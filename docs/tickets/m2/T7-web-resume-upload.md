# M2-T7 — 前端上传页（PDF 选择 → 解析预览 → 出题 → 进房）

- blocking：M2-T3 M2-T6
- 纪律：先写失败测试（红），再实现（绿）；网络只 mock 边界

## 目标

`/interview` 入口：选 PDF → 上传并出题 → 预览解析结果（章节/技能/项目）→ 进入面试房间。
旧项目这条链路有 294 行主 hook + 假三段进度 + 双源预览，M2 留其形、去其繁。

## 交付物

- `src/api/client.ts` 扩展：`createInterviewSession`、`uploadResumeAndGenerateQuestions`（multipart）、
  `getInterviewSession`、`answerQuestion`、`restoreInterview`、`finishInterview`、`getReport`
  （类型全部来自再生成的 `schema.d.ts`）
- `src/interview/useResumeUpload.ts`（controller-hook）：文件校验（`%PDF-` 魔数 + 大小上限）、
  `FileReader/URL.createObjectURL` 本地预览、上传进度三态、失败提示（**解析失败要能看懂原因**）
- `src/pages/InterviewIntroPage.tsx`：简历选择/拖拽、题目数量与模型选择、开始按钮、
  历史面试入口（「继续上次面试」→ restore）
- `src/pages/interview/ResumePreviewCard.tsx`：解析结果预览（章节折叠 + 技能 chips + 项目列表），
  明确标注「解析自本地规则，不由 AI 生成」
- 测试：文件类型/大小拒绝、解析失败文案、上传 → 出题 → 跳转 `/interview/room/:id` 的顺序、
  继续面试入口走 restore

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 新增用例全绿 |
| `pnpm -C apps/web typecheck && pnpm -C apps/web lint` | exit 0 |
| 真实演示 | 上传一份真实 PDF → 看到解析预览 → 点开始进入房间 |

## 形态提议（待确认）

- 上传用 `FormData` + 原生 fetch（不引 axios）；进度用 `xhr.upload.onprogress`（fetch 没有上传进度）。
- 前端不做 PDF 解析（后端唯一解析点），本地预览只显示原始文件信息。

## 不做

- 不做拖拽排序/多文件、不做简历编辑、不做本地解析兜底。
