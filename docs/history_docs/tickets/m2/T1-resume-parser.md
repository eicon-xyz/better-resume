# M2-T1 — resume-parser 混合解析（确定性，无 LLM）

- blocking：M1
- 纪律：先写失败测试（红），再实现（绿）；**纯函数 + 无网络**

## 目标

D10：`parse(pdf: bytes) -> ResumeContext` —— pdfplumber 提文本 → 章节启发式（关键词/字号/
加粗特征打分 + CJK 回退）→ Pydantic `ResumeContext{contact, sections, skills, projects}`。
解析不靠 LLM（可测可控），出题才靠 LLM。

## 交付物

- `better_resume/resume_parser/pdf.py`：pdfplumber 逐页取字符块（保留字号/加粗/位置），
  产出中间结构 `TextBlock(text, size, bold, page, top)`
- `better_resume/resume_parser/sections.py`：章节启发式
  - 关键词表（教育/工作/项目/技能/自我评价 中英双语）
  - 打分：关键词命中 + 字号大于正文 + 加粗 + 独立成行 的加权分
  - 无匹配时按「最短可信章节」回退，仍失败则把全文作为单章节（不丢内容）
- `better_resume/resume_parser/extractors.py`：contact（邮箱/电话/链接正则，CJK 姓名启发式）、
  skills（技能行/逗号分隔/标签式）、projects（项目标题 + 要点抽句）
- `better_resume/resume_parser/parser.py`：`HybridResumeParser` 组装 + `text_layer_missing` 标记
- `better_resume/resume_parser/errors.py`：`ResumeParseError`（非 PDF/加密/无文本层）
- 测试：**合成 PDF fixture**（reportlab-free：用最小 PDF 字节 + 纯文本路径测试）+
  纯文本层 fixture（中英各一份）+ 边界（空文件、扫描件无文本层、超长行、CJK 无空格）
- 夹具放 `tests/fixtures/resumes/`，含一份「真实排版」的 PDF（你提供的或我合成的）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/resume_parser` | 全绿（含扫描件降级用例） |
| 章节识别 | 一份中英混排简历能切出 教育/项目/技能 三类章节且内容不丢 |
| CJK 回退 | 无空格中文简历的 skill 抽取命中率 ≥ 抽检基线（用例固化） |
| 不联网 | 全部用例在断网/无 key 情况下通过 |

## 形态提议（待确认）

- 解析器是**同步纯函数**（CPU 任务）；HTTP 层用 `run_in_threadpool` 调它，别阻塞事件循环。
- 不引 LLM 兜底解析（D10 的分工哲学）；解析不出来就诚实报 `ResumeParseError`，让用户换文件。

## 不做

- 不做 OCR（扫描件直接报错并提示）；不做多栏复杂排版还原；不做简历美化/导出。
