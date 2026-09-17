# P3 提案：星云的"阿里等价物"——百炼应用调用（app_id 形态）端到端验证

> 依据：`docs/tickets/p1-post-v/P1-C-EVIDENCE.md`（星云工作流真机未验证，等价物 = 百炼应用调用）、
> `docs/MANUAL-TESTING.md` §3（"等你输入才能测的"）、用户 2026-09-17 提供 **app_id**（已存入仓库根 gitignored `.env`，
> 变量名 `BR_DASHSCOPE_APP_ID`，**不入库、不进票据、不写日志**）。
> 状态：**范围 B 已获用户确认（2026-09-17）**；实现已落地（见 §9），**真机 1–2 次调用仍待用户点头**
> （纪律：真机调用不擅自跑）。

## 1. 为什么值得做（不是补作业）

P1-C 的验收口径里留了一句：两个保留 adapter 是"**真接缝**"不是"死代码"。现在：

- 讯飞 AST 缝：已被 P1-C 用百炼实时 ASR **覆盖同类能力**（非同一协议，原 adapter 仍标未验证）；
- **星云工作流缝**（云端持有 prompt，我们只做①输入映射②输出契约强校验）：**至今只在假上游下验过，零真机证据**。

百炼"应用调用"是同一形态的阿里实现——控制台建应用 = 云持有 prompt，`app_id` = 绑定目标——
所以它是这条缝的**等价物**：把它跑通，等于在第二家平台上证明"换供应商不发版"这个卖点成立。

## 2. 现状（本窗口实测，不是印象）

| 事实 | 证据 |
| --- | --- |
| 代码里只有两个 adapter：`openai_compat`（DeepSeek / 百炼 OpenAI 兼容）、`xingyun`（`xchen-api.xf-yun.com/workflow/v1/chat/completions`，`flow_id` + `Bearer apiKey:apiSecret`） | `apps/api/src/better_resume/llm_gateway/adapters/` |
| **没有**百炼应用调用的实现（`POST /api/v1/apps/{app_id}/completion`，body `input.prompt`，SSE 要 `X-DashScope-SSE: enable`） | 同上目录只有两个文件 |
| `settings/config.py` 已有 `dashscope_api_key`（V3/V4/P1 同一把 key），`extra="ignore"` → 新增 `BR_DASHSCOPE_APP_ID` 不会破坏现有配置 | `config.py` L102–106/163 |
| 真机预算人工记账 **~185 / 200**；`verify.sh` 自带的 `real_calls_spent.txt` 不存在（脚本口径 = 0） | §6 |

## 3. 三个可选范围（请选一个）

| 方案 | 交付物 | 真机调用 | 预估 |
| --- | --- | --- | --- |
| **A 探针级（最小）** | `apps/api/scripts/dashscope_app_probe.py`：直连 app completion，打印协议字段、SSE 增量时序、usage 有无、app 文本能否过 `validate_structured`（结构化场景）+ EVIDENCE | 2–3 次 | 0.3 会话 |
| **B 正式 adapter（推荐）** | A 的全部 **+** `llm_gateway/adapters/dashscope_app.py`（`LlmGateway` 缝的第三个实现）**+** 绑定支持（`target_ref` = app_id）**+** 假 DashScope SSE 服务端契约测试 **+** 真机 1 次 **+** 文档（`skills/repo-map` / 模块 SKILL.md 若有涉及） | 3–5 次 | 0.5–1 会话 |
| **C 只登记** | 仅 `.env` 里的 app_id + "待做"一行 | 0 | 0 |

## 4. 测试与验收口径（A/B 通用）

1. **红-绿 TDD**：先写失败测试（假 DashScope SSE 服务端：帧解析 / `[DONE]` / 脏帧 / 非 200 错误体），再实现；
2. **只 mock 系统边界、测试 hermetic**：单测只打本地假服务端；真机证据单独进 EVIDENCE——**不许拿假的冒充真的**（P19：
   真机响应要带 `usage`；该平台若不返回 usage，就写"平台不返回"，不美化）；
3. **失败面语义**：缺 `BR_DASHSCOPE_APP_ID` → **503 + Retry-After 并点名变量**（P17），不是 500、不是 401；
4. **连接参数显式**：`trust_env=False`（P20）、显式 `timeout`，SSE 关闭要显式收尾（P24 的同类教训）；
5. **不改 REST 模型** → 若改动则必须跑**契约三件套**（`export_openapi.py` → `gen:api` → `extract_api_index.py --check`，M6 P16）；
6. 交付**验收包**：`EVIDENCE.md`（可复跑命令 + 原始输出 + 数字 + 未验证项 + 与提案偏差），由你验收。

## 5. 不做

- 不引 LangChain / 官方 DashScope SDK / 请求层重试库（D04 依赖纪律；继续 httpx 直连 + 自研链）；
- 不把百炼应用设为任何场景的默认 provider（它只是"可绑定的第三个平台"，默认链路不动）；
- 不做百炼控制台侧的建应用/编排（那是你账号里的事）——**也不改你已经建好的那个应用的 prompt**；
- 不重跑 P1 真机套件、不动 soak/nightly 配置。

## 6. 预算（要你确认）

- P1 人工记账 **~185 / 200**（ACCEPTANCE §1）；本提案 A ≈ 2–3 次、B ≈ 3–5 次 → 记账口径约 **188–190 / 200**，仍在封顶内。
- 若你想把这些调用**独立于 P1 封顶**记账（例如 `BR_REAL_CALL_BUDGET` 之外单列"P3 上限 N 次"），请在 Q2 说明。
- **每次真机调用前我会再问一次**；`verify.sh --layer real` 的预算守卫依旧生效。

## 7. 需要你决定

| # | 问题 | 我的建议 |
| --- | --- | --- |
| Q1 | 选 **A / B / C**？ | **B**：这条缝的卖点就值这几百行，且 0.5–1 会话可控 |
| Q2 | 预算上限维持 200，还是给 P3 单列额度？ | 维持 200（B 也在内） |
| Q3 | 若 app 输出不是合法 JSON（结构化场景），算"平台能力边界"还是"我们加重试/兜底"？ | 先如实记边界；兜底另开提案，不在本票夹带 |
| Q4 | 验证通过后，是否把"百炼应用"写进 `docs/DECISIONS.md`（作为"第三家平台接入"的正式决议）？ | 建议写（一句话，附证据链接） |

## 8. 交付物清单（按选定方案裁剪）

- `apps/api/scripts/dashscope_app_probe.py`（探针，A/B）
- `apps/api/src/better_resume/llm_gateway/adapters/dashscope_app.py` + 注册/绑定（B）
- `apps/api/tests/llm_gateway/test_dashscope_app_adapter.py`（红-绿，B）
- `docs/tickets/p3-dashscope-app/EVIDENCE.md`（真机原始输出 + 数字 + 未验证项）
- 相关 `skills/` 与 `HANDOFF.md` / `MANUAL-TESTING.md` §3 状态回填

## 9. 实施记录（范围 B，2026-09-17）

用户选定 **B（正式 adapter）+ 开分支 PR**。落地内容：

| 层 | 交付物 | 红-绿证据 |
| --- | --- | --- |
| adapter | `llm_gateway/adapters/dashscope_app.py`（`LlmGateway` 缝第三个实现） | 新测试文件 12 例（先红：模块不存在 → 绿；其中 1 条红是**测试自身 bug**，修 helper 后绿） |
| 输入映射 | `scene_mapping.to_dashscope_app_payload`（云侧 prompt 归应用，我们只发 `input.prompt` + 可选 `input.session_id`） | `test_payload_never_sends_our_system_prompt` / `test_session_id_comes_from_the_vendor_context` |
| 工厂与接线 | `dashscope_app_factory.py`（`target_ref` = app_id；key 来自 settings）+ `AdapterKind.DASHSCOPE_APP` + `main.py`/`worker.py` 注册 + `settings.dashscope_app_id/base_url` | 新测试文件 5 例（先红：模块与枚举不存在） |
| 契约套件 | `tests/llm_gateway/test_adapter_contract.py` 增加第三个 harness（同一套 10 条） | 30 passed（10 × 3 实现） |
| REST 契约 | `http/scenes.py` 的 `adapter` Literal 增加 `dashscope_app` | **契约三件套已跑**：`export_openapi.py`（重生成）→ `pnpm gen:api` → `extract_api_index.py --check` 通过 |
| 前端 | AI 设置页可选第三个供应商 + 未配置提示改按 adapter 映射（`BR_DASHSCOPE_API_KEY`） | 前端测试先红（选项缺失、提示错成 XINGCHEN）→ 绿；该页 8 passed |
| 真机探针 | `scripts/dashscope_app_probe.py`（`--dry-run` / 1 次调用 / `--schema` 边界；缺凭据 exit 2、不假装） | 脚本契约：`--help` + 缺凭据拒绝 + dry-run 不花钱（`tests/test_scripts_contracts.py`） |
| 模块导航 | `skills/modules/llm_gateway/SKILL.md`（三个 adapter、新陷阱：`finish_reason` 的字符串 `"null"`、结构化边界） | skills 索引与引用校验测试 39 passed |

本机收口：`bash scripts/verify.sh --layer all` = 12 条命令（后端 **778** / 前端 **175** / contract 全绿）。

### 9.1 真机轮（2026-09-17，用户许可后）

- 真机 **6 次**调用（P1 记账 ~185 → **~191 / 200**）；**结论：应用调用未成功**——供应商对给定 app_id
  一律回 `InvalidParameter: Required parameter(AppId) missing or invalid`（主域名与工作区域名相同）。
  需要你侧确认应用是否已发布、app_id 取值与账号/业务空间是否匹配（详见 `EVIDENCE.md` §4）。
- **真机抓到一个真 bug 并已红-绿修掉（P34）**：供应商用 HTTP 200 + `event:error` 帧报错，修复前 adapter
  把它读成"空答案"（`content=""` + `Done("stop")`）——绑定坏了却给用户空白回答。现在解析 `:HTTP_STATUS/<n>`
  注释、帧里出现 `code` 即抛 `LlmVendorError`（4xx 不可重试 / 5xx 可重试）。
- 证据：`EVIDENCE.md`（原始报文 + 复跑命令 + 诚实清单）、`PROBLEMS.md`（P34）。

