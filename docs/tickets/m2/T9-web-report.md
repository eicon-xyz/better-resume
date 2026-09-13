# M2-T9 — 报告页（SVG 雷达图 + 逐题回放 + 建议）

- blocking：M2-T6 M2-T8
- 纪律：先写失败测试（红），再实现（绿）

## 目标

`/interview/report/:sessionId`：面试结束时给出一页可截图的作品集画面——综合分 + 四维雷达 +
逐题回放 + 建议。

## 交付物

- `src/pages/InterviewReportPage.tsx`：综合分卡 + 雷达图 + 逐题列表 + 建议列表 +
  「重新面试」入口（新建会话）
- `src/interview/RadarChart.tsx`：**自绘 SVG 雷达**（无图表库）：四维轴 + 多边形 + 数值标签，
  支持 0–100 归一与动画（CSS，尊重 `prefers-reduced-motion`）
- `src/interview/reportViewModel.ts`：把后端 `payload` 转成视图模型（维度缺省回退、逐题合并去重、
  综合分标 `estimated` 标记——沿用旧项目「不假装精确」的做法）
- 测试：雷达点计算（含全 0 / 满分边界）、视图模型回退链、逐题回放渲染、
  `summary` 为空时报告仍完整、截图友好（无外部字体/图片依赖）

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | 用例全绿（含边界） |
| 雷达图 | 四个维度各有点位，数值与 payload 一致（用例断言 SVG 属性） |
| 真实演示 | 一页报告可截图进简历/作品集 |

## 形态提议（待确认）

- 不引 recharts/d3（M2 只画一个雷达 + 进度条）；后续真需要图表再评估。
- 报告页只读：数据来自 `interview_reports.payload` 快照，不重新计算。

## 不做

- 不做导出 PDF/图片按钮（可后续加）；不做多次面试对比。
