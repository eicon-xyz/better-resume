# T23 FlowStateMissing 的 HTTP 错误语义（T19 行为收窄的收尾）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/api/`（红线内：http 面的错误映射与对应用例）

## 五栏

- 范围：读 `apps/api/src/better_resume/http/`（错误映射现状与既有 errors 通道）、`interview_engine/flow_store.py` 的 `FlowStateMissing`、AGENTS.md 错误语义条款（响应要能区分「你没登录」「我这边坏了」「数据缺失」）、T19-EVIDENCE 的行为收窄记录。
- 唯一写入路径：`apps/api/` 内——http 错误映射与对应用例。
- 验收口径（原始输出贴进 T23-EVIDENCE.md）：
  1. 红演示：缺 flow 行的会话答题 → 现状（未映射的裸错）的用例先红；
  2. 修后：`FlowStateMissing` 映射为明确响应（状态码与 kind 的选型理由写进实现决定交代；响应体点名缺的是什么），与「未登录」「依赖不可用」可区分；
  3. 用例：缺行答题 → 映射状态码 + 错误 kind；补行后答题恢复正常；
  4. 定向 pytest 绿（隔离库口径见 PROBLEMS.md P15-1），ruff 过。
- 红线：不改 REST 模型字面（`openapi.json`/`schema.d.ts` 不动；若映射必须动它们，停下来报）；不引依赖；不动 p14；不 commit/push/开 PR。
- 不接受的自由度：不许 try/except 吞掉（P01）；不许把缺行静默重建（那是 T19 刚拆掉的读路径写库）；不许发明第二套错误通道（走既有 errors/）。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T23-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`FlowStateMissing` 映射为 500 + `kind=flow_state_missing`（既有 {detail, kind} 通道，detail 点名缺失对象）；红→绿用例含补行恢复路径；REST 模型只读比对逐字节一致。

### 追记（出票方验收）

- 变异演示：换回 HEAD 版 main.py（无映射）→ 用例判红（422≠500），恢复逐字节一致。
- 状态码/通道选型裁决采纳（不重试语义、两维可区分、同形同通道）。
- 票面「裸错」假设由执行方按实测修正为通配 422——正确动作（硬规则 3 口径）。
- 未验证遗留：前端该 kind 无专属中文文案（回落 detail，可接受）；main.py 引证位移并入 T22。
