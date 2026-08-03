# M10 QueryPlanStep 与自检 notes

- [ ] 固定 M10 范围：只做 QueryPlan / QueryPlanStep、plan prompt schema、plan JSON 解析和自检。
- [ ] 红灯测试覆盖合法 plan、缺表、缺字段、非法 Join、敏感字段、多 sql_query step。
- [ ] 读取 M9 SchemaGraph / JoinPath 和 SQL Guard 敏感字段口径，避免 planner 自创第二套事实源。
- [ ] 实现 `engine/nl2sql/planner.py`，不暴露 CoT，不引入多 SQL 执行。
- [ ] 扩展 `engine/nl2sql/prompt.py::build_query_plan_prompt`，Schema 说明从 Pydantic 字段生成。
- [ ] 扩展 `engine/nl2sql/generator.py::extract_query_plan`，兼容 fenced JSON，解析失败映射 `invalid_query_plan`。
- [ ] 跑 M10 聚焦 pytest、必要相关回归和 `git diff --check`。
- [ ] 收工时更新 AI_CONTEXT / dev-log，暂不调用 accept-module。

## 过程记录

- 2026-07-24 红灯：`pytest tests\test_phase3a_planner.py ... pytest-m10-red` 因 `QueryPlanExtractionError/extract_query_plan` 未实现而 collection error，符合 M10 缺口。
- 2026-07-24 决策：QueryPlanStep 使用 `purpose` 表达意图摘要，不加 `thoughts` / CoT；`joins` 用 `relations.yaml` 的 relation id 校验，不接受自由编造 join。
- 2026-07-24 决策：planner 预检敏感字段 `sensitive_field_access`，但不替代 SQL Guard；未知角色或不可用指标映射 `invalid_query_plan`。
- 2026-07-24 绿灯：`pytest tests\test_phase3a_planner.py ... pytest-m10-green-1` 9 passed。
- 2026-07-24 自查补强：`order_by/output_columns` 中出现的 `table.column` 也纳入字段来源和敏感字段预检；`pytest-m10-green-2` 9 passed，`pytest-m10-related-2` 11 passed / 1 既有 warning。
- 2026-07-24 finish 验证：M10 指定命令 `pytest tests\test_phase3a_planner.py ... pytest-m10-tmp` 9 passed；全量 `pytest ... pytest-m10-full` 63 passed / 1 既有 Starlette/httpx warning；`git diff --check` 仅 LF→CRLF 提示。
- 2026-07-24 文档后复检：`pytest tests\test_phase3a_planner.py ... pytest-m10-final-check` 9 passed；`git diff --check` 仍仅 LF→CRLF 提示。
