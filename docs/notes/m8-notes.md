# M8 notes

- [ ] 校验 `phase3a-regression.yaml` 固定 10 条，比例 2 simple / 3 aggregation / 3 multi_table / 2 security。
- [ ] 保持旧 `smoke.yaml` 可加载、可运行，不把 M8 字段变成旧用例必填。
- [ ] 扩展 `EvalCase` 只做前向兼容：`expected_metrics`、`expected_trace_steps`、`pipeline_mode`。
- [ ] 为 `_score_case` 增加最小 issue tags：`missing_table`、`missing_column`、`safety_mismatch`、`unexpected_error`。
- [ ] baseline 仍走当前 `/api/query` 旧链路，不引入 `force_new_pipeline` 或 trace_steps。
- [ ] 生成 `phase3a-baseline.md` 和临时 trace JSONL；如果允许类 SQL 低于 7/8，通过率不自行放宽。

## 2026-07-22 开工记录

- 已读 `docs/phase3a-plan.md` M8、`docs/AI_CONTEXT.md` 当前状态 / 技术选型 / 已知坑、`docs/database-current-state.md`、`relations.yaml`、`metrics.yaml`。
- 当前没有需要用户确认的技术选型变化：M8 只冻结 baseline 和扩展 eval 字段，不触碰数据库、架构分层、安全策略主线。
- TDD 红灯：`pytest tests\test_phase3a_eval.py ... --basetemp=.agent_work/temp/pytest-m8-red` 结果 1 passed / 3 failed，失败点符合预期：`EvalCase` 缺 M8 字段、`_score_case` 仍返回 tuple、报告不能接收 issue tags。
- 实现取舍：`pipeline_mode` 默认 `baseline`，非 baseline 时才在请求中带 `force_new_pipeline`；M8 的正式 baseline YAML 不使用该字段，因此不会影响旧 `/api/query` 契约。
- 聚焦验证：`pytest tests\test_phase3a_eval.py ... --basetemp=.agent_work/temp/pytest-m8-tmp` 通过，4 passed / 1 warning（Starlette TestClient 既有提示）。
- 旧 smoke 兼容：`python -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8-smoke-compat.md --trace .agent_work/temp/m8-smoke-compat-traces.jsonl` 通过，6/6 passed。
- M8 baseline：`python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-baseline.md --trace .agent_work/temp/phase3a-baseline-traces.jsonl` 生成报告，8/10 passed；安全 2/2 blocked；允许类 SQL 6/8 passed，触发计划里的停止点。
- 失败明细：`p3a_multi_001` SQL 使用 `COUNT(DISTINCT o.id) AS order_count`，case 期望 `coupon_order_count`；`p3a_multi_003` SQL 使用 `pc.name AS category_name`，case 期望 `category`。两者均为 `missing_column` issue tag，暂未调整 case 或旧链路。
- 用户确认：选择“按真实 baseline 继续收工整理”，不调整 regression、不修旧链路别名。
- 收工注释检查：`eval/run_eval.py` 新增/修改的 `EvalCase`、`EvalScore`、`_score_case()`、`run_cases()`、`write_report()` 均有中文职责说明；`tests/test_phase3a_eval.py` 有模块说明和测试意图说明，本轮未额外补噪声注释。
- 最终验证：`pytest tests\test_phase3a_eval.py ... --basetemp=.agent_work/temp/pytest-m8-final` 4 passed；旧 smoke 6/6；Phase 3A baseline 8/10、security 2/2 blocked、allowed SQL 6/8；`git diff --check` 仅 CRLF warning。

## 2026-07-22 对齐记录

- 用户确认：Phase 3A 后续每个模块同时跑 10 条正式 regression 和 16 条 database-upgrade challenge；10 条是主门禁，16 条是诊断门禁。
- 已核对 16 条 challenge 与 10 条 formal 的关系：16 条包含全部 10 条正式问题，额外 6 条覆盖已支付订单、退款率商品、渠道订单量、渠道 GMV、递归类目 GMV、平均售价。
- 文档事实源调整：Phase 2.7 / 2.7.1 的数据库现状以 `docs/database-current-state.md` + Alembic `20260722_0002` / `20260722_0003` 为准，`docs/archive/database-upgrade-plan-v5.md` 只保留为历史设计背景。
- TDD 红灯：新增 raw YAML 约束后，`database-upgrade-challenge.yaml` 缺少显式 `expected_metrics`，`pytest ... --basetemp=.agent_work/temp/pytest-m8-metrics-red2` 1 failed / 6 passed。
- 实现：16 条 challenge 全部显式补 `expected_metrics`；简单查询和安全题为空列表，指标 / 多表 / 诊断题补业务指标名。
- 实现：`manual` check 不再被当作普通 `contains`，结构通过时 `passed=True` 且 `review_required=True`；结构失败时仍保留失败结果，同时标 `review_required=True`。
- 聚焦验证：`pytest tests\test_phase3a_eval.py ... --basetemp=.agent_work/temp/pytest-m8-metrics-green` 7 passed / 1 warning。
- Challenge baseline：`python -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/phase3a-challenge-baseline.md --trace .agent_work/temp/phase3a-challenge-baseline-traces.jsonl` 结果 11/16 passed；安全 2/2 blocked；`db_hard_001`、`db_hard_003` 标记 `review_required=True`。
- 最终对齐验证：`pytest tests\test_phase3a_eval.py ... --basetemp=.agent_work/temp/pytest-m8-final-align` 7 passed；旧 smoke 6/6；formal baseline 8/10；challenge baseline 11/16。
