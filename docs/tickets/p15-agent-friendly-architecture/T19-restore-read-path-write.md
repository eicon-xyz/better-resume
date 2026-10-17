# T19 RestoreService.restore 读路径写库缺陷（P15-2）

Type: task
Status: resolved
Blocked by: T16（tests 写面有交叠风险，串行）
唯一写入路径: `apps/api/`（红线内：interview_engine 的 RestoreService/QuestionService 交接缝与对应用例）

## 五栏

- 范围：读 `apps/api/src/better_resume/interview_engine/`（restore 流程、flow_state 派生、QuestionService.initialize）、`pitfalls-report.md` P07（共享状态所有权）与 T13-EVIDENCE 的旁证记录、PROBLEMS.md P15-2。
- 唯一写入路径：`apps/api/` 内——restore/出题交接缝与其用例。
- 验收口径（原始输出贴进 T19-EVIDENCE.md）：
  1. 红演示：复现「无题会话 restore 后出题 → initialize 主键冲突」的用例先红；
  2. 修后：读路径不再写库（派生态要么只读、要么由唯一写入方负责创建），同一用例绿且重复跑不漂（幂等）；
  3. `grep -rn "flow_state" apps/api/src/better_resume/interview_engine` 的写点逐条注明所有者；
  4. 定向 pytest 绿（隔离库口径见 PROBLEMS.md P15-1），全量由出票方终验。
- 红线：不改 HTTP 面与 REST 模型；不引依赖；不动 p14；不 commit/push/开 PR。
- 不接受的自由度：不许用 try/except 吞主键冲突蒙混（P01 类）；不许把写库挪到第二个地方形成双写（写入方唯一）；不许为过用例放宽幂等语义。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T19-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`_derive` 改为只读内存构造，`interview_flow_state` 创建方唯一留在出题写入方；双用例红→绿，定向 75/75 连跑两遍零漂移。

### 追记（出票方验收）

- 变异演示：换回 HEAD 版 restore_service.py（老 bug 形态）→ 双用例判红（IntegrityError 现形），恢复逐字节一致。
- IE-10 行位移的红裁决：留 T22 重锚（本票不动 units，红线保持）。
- 行为收窄确认为预期（读路径只读、响亮失败）；`FlowStateMissing` 的 HTTP 语义 → T23 收尾。
