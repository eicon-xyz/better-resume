# interview-engine

## 职责

面试全链路 —— 两层状态机、出题、答题评分、追问裁决、恢复、报告聚合。

## 对外接口

`SessionService/AnswerService/QuestionService/FollowUpService/ReportService/RestoreService`、
`decide_follow_up`（纯函数）、`QuestionLockRegistry` / `RedisQuestionLockRegistry`、`HotStateStore`、
`decide_category` / `plan_questions`（纯函数）、`corpus.load_corpus` / `corpus.filter_corpus`。

## 不变量

1. **状态机是唯一写入口**：session（draft→…→finished）与 flow（init→asking→evaluating→follow_up→completed）
   两层联动；非法转移抛错，version CAS 防并发写。
2. 幂等：`(session_id, request_id)` 唯一约束 + 回放既有响应，重投不重复计费。
3. 题级锁：同题并发只有一个进入评分；评分失败回滚到可重答（不吞答案）。
4. 访问题号必须是"当前题"，否则 409；别人的会话一律 404。
5. 报告是**冻结快照**：finish 幂等，数字全部聚合得出，LLM 只写一段总结（失败不影响数字）。
6. 热层只是缓存：Postgres 是唯一真相，`source=hot/derived` 标明来源，写路径提交后失效缓存。
7. **类别由模型提议、引擎裁决**：`GeneratedQuestion.category` 是受控枚举，非法或缺失一律走规则回退
   （引用项目名 → `project`，引用实习段 → `internship`，否则 `fundamentals`）；追问继承主问题的类别。
8. **语料是发布物不是运行时资源**：`corpus/questions.json` 随包发布，缺文件 / 坏 JSON 抛 `CorpusError`
   （硬失败，不是降级）；过滤后没匹配才算降级，响应带 `degraded_reasons`。

## 已知陷阱

- 追问与评分是同一次请求里的两个 AI 调用：`AnswerService.submit` 的 `follow_up_gateway` 可选参数
  就是为场景路由加的；删掉它会让 FOLLOW_UP 绑定失效。
- 用"第 N 次出现"打文本补丁把 `http/interview.py` 改坏过一次：改这个模块前先看测试地图，
  改完必须跑 `tests/test_interview_*_api.py`，不要盲打补丁。
- 追问上限按主题重置；题号是值对象（`2-F1`），不要用字符串拼接解析。
- `report summary` 异步化后，`GET report` 可能返回 `summary_pending`，数字仍然可用。
- 语料按**技能词级**匹配（ASCII 整词、CJK 子串），所以 `Java` 不会命中 JavaScript 题；改 `TOPIC_ALIASES`
  要连带跑 `tests/interview_engine/test_corpus.py`。
- 报告「按类给分」是确定性聚合：某类计分题 < 2 时不给分数、写「样本不足」；改阈值或评语要同步改前端
  `THIN_SAMPLE` 比较（否则一行会重复显示「样本不足」）。

## 测试地图

`tests/interview_engine/`（FSM 穷举、评分、追问、报告）+ `tests/test_interview_*_api.py` + `tests/test_hot_state.py`。

## 常见变更配方

改答题流程：先改 FSM 转移表 → 穷举测试 → 服务 → HTTP → 幂等/回滚用例必须仍然绿。
