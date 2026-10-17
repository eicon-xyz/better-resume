# T25 远端状态只读可见（建议 13 的工具半边）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/pr_state.sh`（新建，一个文件）

## 五栏

- 范围：读 `recall-report.md` F18（PR/合并状态对智能体不可见）、`docs/agents/subagents.md`、gh 的只读子命令。
- 唯一写入路径：`scripts/pr_state.sh`（内置 --selftest）。
- 验收口径（原始输出贴进 T25-EVIDENCE.md）：
  1. `bash scripts/pr_state.sh` 输出当前分支的 PR 状态（number/state/base/head 或「无 PR」），gh 不可用/未登录时响亮失败（非 0 + 点名原因）；
  2. 只读自证：脚本内只有 gh 的 GET/view 类调用，`grep -nE "gh .*(create|merge|close|edit|push)"` 命中 0；
  3. `--selftest` 退出 0（好/坏路径各至少一例，坏路径含 gh 缺失模拟）。
- 红线：不写远端（硬规则 1：合并/建 PR 永远是用户的动作）；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：不许把「无 PR」与「gh 坏了」混成同一种输出；不许缓存远端状态（每次现读）；不做 HANDOFF 生成物 --check（属会话工具链，见实现决定交代）。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`scripts/pr_state.sh` 落地：只读 `gh pr list`、无 PR/环境坏/调用失败三种读数各自点名（0/2/1 退码）、自检 10 项断言；变异证明绿→红→绿。

### 追记（出票方验收）

- 复跑：自检 10/10、真跑「无 PR」exit 0、写动词 grep 0 命中；我方用 `verify_mutation.sh` 复跑绿→红→绿。
- 执行方主动交代的 trap/局部变量越界写 /gh-* 已清理复核（ls 三处均 No such file）。
- 退出码语义（0/1/2）选型采纳；HANDOFF --check 与 verify.sh 接线按票面不做。
