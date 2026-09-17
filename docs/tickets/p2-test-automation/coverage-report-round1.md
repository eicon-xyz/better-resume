# P2-T6 第一轮：覆盖率报告（先报告，后设底线）

- 时间：2026-09-15；命令：`pytest --cov=better_resume`（pytest-cov 7.1.0）+ `vitest run --coverage`（@vitest/coverage-v8 5.0.0）
- 原始产物：`var/evidence/coverage-api.json`（后端 JSON）；前端覆盖率表见下

## 后端（总计 **95.0%**，5525/5813 行，288 行未覆盖）

| 模块 | 覆盖行 / 语句 | 百分比 | 深模块（§5.5 清单） |
| --- | --- | --- | --- |
| ai_resilience | 922/961 | **95.9%** | ✅ 设底线 |
| interview_engine | 1206/1267 | **95.2%** | ✅ 设底线 |
| media | 851/908 | **93.7%** | ✅ 设底线 |
| identity | 226/238 | **95.0%** | ✅ 设底线 |
| jobs | 107/112 | **95.5%** | ✅ 设底线 |
| llm_gateway | 742/776 | **95.6%** | ✅ 设底线 |
| resume_parser | 259/278 | **93.2%** | ✅ 设底线 |
| conversation | 174/177 | 98.3% | 浅 |
| http | 534/556 | 96.0% | 浅（路由壳） |
| settings | 113/114 | 99.1% | 浅 |
| observability | 54/55 | 98.2% | 浅 |
| chat | 134/139 | 96.4% | 浅 |
| db | 13/16 | 81.2% | 浅（引擎装配） |
| worker.py | 91/112 | 81.2% | 含心跳/健康检查（P26 修复后仍有未覆盖分支：降级路径的日志分支） |

## 前端（总计 **87.02%** statements / 88.27% lines，161 测试全绿）

## 第二轮（设底线，待你点头后执行）

- 深模块底线：**≥90%**（当前全部 ≥93.2%，底线只是钉住现状、防止回退）；
- `worker.py` 与 `db` 不设线（装配/编排薄层，且 worker 的降级日志分支需要注入时钟才能覆盖——成本大于收益）；
- 前端暂不设底线（组件层 87% 已高于本项目历史水平；如需，另设 per-file 最小集）。
- 落地方式：`verify.sh --layer coverage` + `(fail_under)` 断言，或 CI 里 `coverage report --fail-under=90 --include=...`。

## 复跑

```bash
cd apps/api && uv run pytest -q --cov=better_resume --cov-report=term --cov-report=json:../var/evidence/coverage-api.json
cd '/root/better resume' && pnpm -C apps/web exec vitest run --coverage
```
