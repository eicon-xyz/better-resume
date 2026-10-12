# T4b — 模块契约：interview-engine / resume-parser / media

- blocking：T2

## 目标

同 T4a，落另外三个模块的 Protocol + 类型 + 占位实现 + 合约冒烟测试。

## 交付物

- `better_resume/interview_engine/`：`UserId` / `SessionId` / `ResumeUpload` / `AnswerTurn` /
  `SessionHandle` / `SessionView` / `TurnResult`（`score` / `feedback` / `missing_points` /
  `next: Question | FollowUp | Finished`）、`InterviewEngine` Protocol（`start` / `answer` /
  `restore` / `finish`）
- `better_resume/resume_parser/`：`ResumeContext`（contact/sections/skills/projects）、
  `ResumeParser` Protocol（`parse(pdf: bytes) -> ResumeContext`，M0 同步签名照抄 §12.2）
- `better_resume/media/`：`ChannelCtx` / `VoiceSpec` / `AudioRef`、`TranscriptionChannel` Protocol
  （`start` / `feed` / `stop`）、`TtsSynthesizer` Protocol（`synthesize`）
- 占位实现 + `tests/contracts/test_*_contract.py`

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python -c "import better_resume.interview_engine, better_resume.resume_parser, better_resume.media"` | exit 0 |
| `uv run pytest -q tests/contracts` | 全绿 |
| 人工核对 | 四个 engine 方法 + 两个 media Protocol 与 §12.2 一致 |

## 形态提议（待确认）

- 值对象（`QuestionNo`、`RequestId`）在 M0 只做类型别名/轻量 NewType，语义与不变量归 M2。

## 不做

- 不做状态机、不做 pdfplumber 解析、不连讯飞 WS（M2/M4）。
