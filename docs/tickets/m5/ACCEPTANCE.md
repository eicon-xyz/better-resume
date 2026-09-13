# M5 验收证据（星云 WorkflowAdapter：双 adapter 对照）

> 日期：2026-09-14 ｜ 分支：m5/scene-bindings ｜ 票据：docs/tickets/m5/（T1–T9 完成；T10 待凭据）
> 验收口径（§12.4 原文）：**场景绑定切换供应商不改业务码**。

## 1. 结论

| 项 | 结果 |
| --- | --- |
| §12.4 验收 | ✅ 同一场景改一行绑定就把供应商从 openai_compat 换成 xingyun，**业务服务层零改动**（§2 的 diff 证据）；五个场景各自的绑定都在路由测试里被证明生效 |
| ⚠️ 星云真机 | **未验证（缺凭据）**：`XINGCHEN_API_KEY` / `XINGCHEN_API_SECRET` / 每场景 flow_id 本机没有；协议实现只有本地假服务端的契约测试与 parity 对照（§6） |
| 后端测试 | **528 passed**（M4 473 → +55） |
| 前端测试 | **158 passed**（M4 152 → +6） |
| 迁移 | 新增 `llm_scene_bindings`（9f2c1a7b5d31，五场景默认绑定 openai_compat → 行为与 M4 完全一致） |
| 本地 CI 矩阵 | **12/12 全绿**（§4） |
| 问题台账 | `docs/tickets/m5/PROBLEMS.md` P0–P4 |

## 2. 「不改业务代码」的机器可验证证据

```
git diff --stat main...HEAD -- apps/api/src/better_resume/interview_engine \
    apps/api/src/better_resume/chat apps/api/src/better_resume/llm_gateway/adapters/openai_compat.py

 apps/api/src/better_resume/interview_engine/answer_service.py | 8 +++++++-
 1 file changed, 7 insertions(+), 1 deletion(-)
```

那 7 行是**唯一**的服务层改动：给 `AnswerService.submit/_submit_locked/_persist_result` 加了一个可选参数
`follow_up_gateway`（默认 None → 回落到主 gateway），因为一次答题同时触发「评分」和「追问」两个场景，
而 M2 的服务只接收一个 gateway。**没有任何一行是为"支持星云"而写的分支**：状态机、幂等、题级锁、
聊天服务、OpenAI adapter 全部未改，M1–M4 的 501 条既有用例一行未改、全部通过。

路由证据（`tests/test_scene_routing.py`，5 例）：

| 用例 | 断言 |
| --- | --- |
| 出题走 QUESTION_EXTRACTION 绑定 | 切到 `xingyun:flow-questions` 后，上传端点确实调用被绑定的 adapter（记录 binding），返回结构不变 |
| 答题走 ANSWER_EVALUATION + FOLLOW_UP | 同一次请求里两个场景各自解析到自己的绑定 |
| 结束走 REPORT_SUMMARY | 端点先解析场景再进业务（draft 会话 409 也证明解析发生在前） |
| 未配置场景 | 503 + `not configured`（不是 500、不静默换供应商） |
| 显式 model_ref | 仍然覆盖场景绑定（M1 的模型选择器不退步） |

## 3. 双 adapter 契约矩阵（M5-T5）

一套 10 条契约，两个实现（`tests/llm_gateway/test_adapter_contract.py`，20 例）：
非流式返回 / 结构化输出 / 流式序列 / reasoning 分流 / schema 失败重试一次 / 5xx 可重试 /
4xx 不可重试 / 超时分类 / 注入防御 / 提前关闭流后仍可用。

**突变校验（证明套件有鉴别力）**：把星云 adapter 的 reasoning 帧故意改成 `ContentDelta` 后：

```
mutated tests 20 failures 1 errors 0   →  caught by: test_reasoning_never_mixes_into_content[xingyun]
reverted tests 20 failures 0 errors 0
```

## 4. 双供应商对照（M5-T8，真 DeepSeek vs 假星云）

`uv run python scripts/adapter_smoke.py --scene answer_evaluation`：

```
  openai_compat      5095.9 ms  chars= 876  fields=['feedback', 'follow_up_needed', 'missing_points', 'score']
xingyun: local fake workflow at http://127.0.0.1:.../workflow/v1/chat/completions (contract-level evidence)
  xingyun               4.0 ms  chars=  66  fields=['feedback', 'follow_up_needed', 'missing_points', 'score']

parsed field parity: True (['feedback', 'follow_up_needed', 'missing_points', 'score'])
```

耗时差异是"真实网络 vs 本地假服务端"，不是性能结论（这里不做性能对比，避免假数字）。
契约级一致性由 `tests/test_adapter_parity.py` 固定：同一输入两个 provider 的 parsed 字段集合相同、
超时/401 的错误分类相同。

## 5. 本地 CI 矩阵（12/12）

```
PASS 01 uv sync --frozen        PASS 07 openapi --check
PASS 02 ruff check              PASS 08 pnpm install --frozen-lockfile
PASS 03 ruff format --check     PASS 09 web lint
PASS 04 pytest (528)            PASS 10 web typecheck
PASS 05 alembic upgrade head    PASS 11 web test (158)
PASS 06 alembic check           PASS 12 web check:api
```


## 6. 未验证项（明确列出）

1. **星云真机**：无凭据 → 真实 SSE 帧形状、输出字段名、错误码语义、鉴权是否被接受，全部未验证。
   复跑：`XINGCHEN_API_KEY=... XINGCHEN_API_SECRET=... uv run python scripts/adapter_smoke.py --scene answer_evaluation --real-xingyun`
   （还需要 `--flow` 指向真实 flow_id；T10）。
2. **云端工作流提示词行为**：星云是黑盒编排，我们只验证"传什么/怎么解析回来"；云端是否严格按
   `expect_fields` 输出 JSON，只有真机能回答。因此我们的策略是**输出强校验 + 失败明确报错**，
   而不是别名兜底（见 P0）。
3. **多实例绑定一致性**：绑定缓存是进程内的，改绑定只对当前实例立即生效（多实例留 M6）。
4. **真实浏览器**：`/settings/ai` 面板的交互由 jsdom 测试覆盖，未做人工点击（与本机无头环境一致）。

## 7. 与提案的偏差

1. **唯一服务层改动**：`AnswerService.submit` 增加可选 `follow_up_gateway`（见 §2），
   提案里写的"服务层零改动"因此修正为"零*业务*改动：仅新增一个可选参数用于路由两个场景"。
2. **星云 adapter 的流式实现**：`complete()` 走 SSE 收集（星云 API 只有流式路径），
   因此"非流式"在我们这一侧是"收集完再校验"，对外契约与 OpenAI 路径一致。
3. **重试只有一个 owner（延续 M3）**：星云 adapter 的重试只包在"打开连接"这一层，
   不再叠加第二层（PROBLEMS P4 记录了这个坑：嵌套重试让 5xx 变成 4 次调用）。
4. **绑定缓存失效点**：`PUT /scenes/{scene}` 后主动失效该场景；`GET` 直接读库（不走缓存），
   因此列表永远显示最新值，而解析路径走向缓存。
5. **废弃的占位**：`UnimplementedWsTicketStore` 之外，M0 的 `media/placeholder.py` 仍在（M4 未删）；
   M5 无新增占位。
6. **未做**：按用户/按会话的绑定（Q3）、绑定审计历史、配置热推送、星云文件上传。

## 8. 复跑方式

    # 后端（本机原生库）
    export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
    export BR_REDIS_URL='redis://127.0.0.1:6379/0'
    cd apps/api && uv run pytest -q                        # 528 passed
    uv run python scripts/adapter_smoke.py --scene answer_evaluation   # §4 的对照表

    # 前端
    pnpm -C apps/web test --run                             # 158 passed

