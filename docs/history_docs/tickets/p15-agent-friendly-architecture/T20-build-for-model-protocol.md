# T20 build_for_model 收进工厂协议（LG-06 收尾）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/api/src/better_resume/llm_gateway/` 与 `docs/audit/units/llm_gateway.json`

## 五栏

- 范围：读 `apps/api/src/better_resume/llm_gateway/resolver.py`（`build_for_model` 的 getattr 私约，约 :180）、工厂协议（T12 的 `config_status` 形态）、`docs/audit/units/llm_gateway.json` LG-06、`pitfalls-report.md` P08 与设计红旗「information leakage」。
- 唯一写入路径：llm_gateway 模块与 llm_gateway.json（LG-06 的 why 刷新 + fix_record）。
- 验收口径（原始输出贴进 T20-EVIDENCE.md）：
  1. 红演示：缺 `build_for_model` 的工厂被 getattr 私约动态取用的用例先红（静默降级形态）；
  2. `build_for_model` 进 Protocol，缺方法响亮失败；`grep -n "getattr" apps/api/src/better_resume/llm_gateway` 私约清零或逐条注明；
  3. LG-06 记 `fix_record`（fixed，带证据指针）并把 why 刷成当前形态；
  4. `uv run --project apps/api python scripts/verify_audit_evidence.py --strict` 退出 0；定向 pytest 绿（隔离库口径见 PROBLEMS.md P15-1）。
- 红线：不改场景绑定语义与 HTTP 面；不动其他 units 条目；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：不许兼容 shim（协议违约响亮失败，与 T12 同口径）；不许只刷 why 不改代码；不许给 LG-06 之外的条目记 fix_record。

## 红绿纪律

先红后绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T20-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

`build_for_model` 成为 GatewayFactory 第三成员，getattr 私约清零（resolver 归零，余 scene_mapping 的防御读已注明）；LG-06 记 fix_record(fixed) 并刷 why；红→绿两用例钉住；隔离库全量 1011/0/0/0。

### 追记（出票方验收）

- 变异演示：把 getattr 私约兜底放回 resolve_model → `test_a_factory_without_model_selection_fails_loudly` 判红，恢复逐字节一致。
- `--strict` 复跑 122/0/0；getattr 扫描与自述一致。
- LG-07/LG-09 的引证移位 → 并入 T22 收口重锚（连同 MODULE-AUDIT.html 重建）；「非 openai_compat 工厂不实现该钩子」未钉用例，已记 fix_record.unverified。
