# T15 部署与连接默认值单一声明（建议 4）

Type: task
Status: resolved
Blocked by: T14（协议契约测试是消费方之一，先落地）
唯一写入路径: `scripts/`（红线内：只动 `compose_smoke.sh` 与新增的默认值声明文件；`verify.sh` 与其他脚本不碰）

## 五栏

- 范围：读 `scripts/compose_smoke.sh`、`compose.yaml`、`deploy/nginx.conf`、`docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md` P02/P11（缓存头、代理、迁移、非 root 属主、upstream 解析、WS 超时）、T14 的契约测试（连接参数消费方）。
- 唯一写入路径：`scripts/` 内——新增默认值声明文件（单一真源）+ `compose_smoke.sh` 消费改造。
- 验收口径（原始输出贴进 T15-EVIDENCE.md）：
  1. 红演示：声明里删掉任一条默认值的断言 → 对应检查必红（证明声明与断言真绑定）；
  2. 每条隐式默认值（缓存头/迁移步骤/非 root/upstream 解析/WS 超时）都有且只有一处声明，并有一条真跑该形态变红的断言；
  3. `bash scripts/compose_smoke.sh` 全绿（真跑栈的读数；栈不在就先按 docs/HANDOFF.md §3 起栈并注明）；
  4. `bash scripts/verify.sh --layer scripts` 仍退出 0。
- 红线：不改 compose.yaml / deploy/nginx.conf（它们是被声明描述的对象；发现真的要改就停下来报）；不碰 verify.sh；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：不许出现两份默认值清单（声明文件是唯一真源，脚本读它）；不许「跑通即可」式断言（每条断言要数得出值）；不许把测试形态默认值写死在断言里绕过声明。

## 红绿纪律

先红后绿：断言绑定演示先行。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`scripts/deploy_defaults.sh` 成为部署默认值唯一真源（5 条声明），`compose_smoke.sh` 消费并真跑判定；3 组红演示（清字段/改值/删记录）全红、还原逐字节一致。

### 追记（出票方验收）

- 冒烟复跑 ALL CHECKS PASSED exit 0；变异演示：声明 300s→301s → 「the running nginx carries the declared read timeout」判红，恢复一致。
- 写入面恰两文件；`--layer scripts` 12/12（T17/T15 两份读数），终验留到 T20 落地后（audit units 在飞会短暂红）。
- 环境事实裁决：compose v5.6.0 无 COMPOSE_BAKE、P45 出口失效 → P15-8 + T21 排队票（用原型定修复方向，不擅改构建面）。
- compose 栈保留运行（F11：你要人工拍页面时直接用 http://127.0.0.1:8080），停用命令 `docker compose --profile smoke down -v`。
