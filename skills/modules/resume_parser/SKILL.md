# resume-parser

## 职责

确定性简历解析（pdfplumber → 章节启发式 → `ResumeContext`）。**不调用 LLM**（D10）。

## 对外接口

`HybridResumeParser.parse(bytes) -> ResumeContext`、`ResumeParseError`（带 code）。

## 不变量

1. 解析结果只来自 PDF 文本；缺字段就是缺字段，不猜、不编。
2. 扫描件/坏文件/超限 → 明确错误（HTTP 400 + code），并且会话留在可重试状态。
3. 同一份简历内容（sha256）只落一份文件。

## 已知陷阱

- CJK 无空格：分词靠章节关键词 + 字号/加粗启发式，正则别假设空格（见 `sections.py`）。
- 测试用 `tests/interview_engine/test_parser_helpers.py` 生成 PDF：**别在仓库里塞二进制样本，
  也别用 shell/heredoc 手工转义样本内容**——转义反复踩坑之后加了源码 hygiene 守卫（M4 P7）。
- 解析器是"确定性"卖点：任何"猜一个默认值"的补丁都会让同一份简历在不同版本给出不同结果。

## 测试地图

`tests/resume_parser/`（章节打分、抽取器、端到端解析）。

## 常见变更配方

加一个章节类型：关键词表 → 打分函数 → 用例（命中/未命中/干扰）。
