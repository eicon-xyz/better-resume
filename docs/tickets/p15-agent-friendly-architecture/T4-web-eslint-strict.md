# T4 前端吞失败收紧为编译期错误（建议 2）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/web/` 目录内——eslint.config.js 与 lint 点名的吞失败调用点

## 五栏

- 范围：读 `apps/web/eslint.config.js`、`apps/web/src/**`（重点 `void xxx()` 形态）、`docs/tickets/p15-agent-friendly-architecture/pitfalls-report.md` P01、`docs/tickets/p15-agent-friendly-architecture/README.md` 建议 2 与原型结论 A。
- 唯一写入路径：`apps/web/`（eslint.config.js + 被点名调用点的最小修复）；不碰 apps/api、docs、scripts。
- 验收口径（三条命令可复跑，原始输出贴进 T4-EVIDENCE.md）：
  1. 红演示：fixture（见附录）写入 `apps/web/src/__red_demo__.tsx` 后 `cd apps/web && ./node_modules/.bin/eslint --no-ignore src/__red_demo__.tsx` 报出 `no-floating-promises` 与 `no-void` 共 ≥3 error，同一命令内删除 fixture；
  2. 绿收口：`cd apps/web && ./node_modules/.bin/eslint src` 退出码 0；
  3. 配置读数：`./node_modules/.bin/eslint --print-config src/App.tsx` 中 `no-floating-promises` 的 `ignoreVoid` 为 false、`no-void` 为 error。
- 红线：不新增依赖（typescript-eslint 已在）；不动 lint 没点名的文件；不 commit/push/开 PR；p14 在飞的未提交改动若被点名，只做最小修复并在「实现决定交代」记明。
- 不接受的自由度：不许把吞失败改成静默 catch（失败必须进既有 errors 通道）；不许用 eslint-disable 绕过（行级豁免必须注明理由）；不许改公开接口签名；不许重排无关代码。

## 红绿纪律

先跑红演示（fixture 变红）再改配置与调用点。fixture 附录：

```tsx
export function RedDemo(props: { onSubmit: (t: string) => Promise<void> }) {
  void props.onSubmit("");
  props.onSubmit("");
  return null;
}
```

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行：我理解这票解决什么 / 我怎么做，到文件粒度 / 我不做什么）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。

## Answer

eslint 收紧（ignoreVoid:false + no-void）落地，13 文件点名调用点最小修复；红演示 3 errors、eslint/tsc 绿、vitest 237 全过；变异演示：ignoreVoid 翻回 true → 恰好 2 problems，规则确实钉住行为。

## Comments

- 出票方裁决：Button.tsx 的 caller className 合并虽非 void 形态，属同一错误类（调用方输入被静默丢弃），采纳；ChatPage actionError 横幅是「失败必须进错误通道」的最小落地，采纳；capture.ts 行级豁免无红演示，接受书面理由，出现真实失败面再补。p14 在飞文件只动点名 void 点（mtime 与 diff 面已核，会话外改动零归属）。
