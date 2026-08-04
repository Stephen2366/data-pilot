# M22 Eval Contract / Semantic Output Stabilization Notes

## 开发中素材

### 已确认的长期口径（2026-08-04）

- 用户确认先修正 case / scorer 契约，再评估 pipeline；M21 `21/32` 保留为历史快照，M22 后的分数不得直接宣传为模型提分。
- 用户确认商品退款率以 `refunds.order_item_id -> order_items.product_id` 的订单明细归因为唯一默认口径；`orders.product_id` 只保留为兼容关系，不再作为本题 reference。
- 用户确认“一级类目”使用 `products.category_id -> product_categories` 规范类目树；不再用 `products.category` 兼容字段作为默认事实。
- 用户确认 manual / diagnostic 分开展示：报告新增自动能力分、人工审查分和 case/scorer 契约重分类清单。

### 已实施的关键设计

- Context Contract 从同请求 JSONL trace 的 `schema_context.metadata.tables/fields` 读取 SchemaGraph 证据，不再拿最终 `body.columns` 充当内部上下文；API 响应契约不新增字段。
- `plan_validation_blocked` 进入专属 scorer 优先路径，结构化语义拒绝不会被空输出列或 allow 安全状态抢先遮蔽。
- 新增窄范围 `semantic_validation`：仅识别当前 Schema 明确没有 supplier 字段、知识库文档到订单无归因关系、以及显式多步对比三类已证实的不支持需求；统一返回 trace 可见的 `blocked_via=semantic_request_validation`，不把它们伪装成 LLM generation error。
- SQL generation 增加 QueryPlan 已显式给出的 `order_by` / `limit` 合同检查；不分析或改写任意 SQL，避免泛化正则规则误拦合法语句。
- 新增 `coupon_order_count` 派生指标会让 Schema document corpus 从 193 增至 194；当前 hash 为 `58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f`。这是用户确认“优惠券使用订单数”单独建模的直接结果，不切换 embedding / Milvus / fusion，但后续 retrieval 对照必须记录新 hash，不能与 M21 的 193-doc hash 混用。

### 中途验证快照

- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_eval.py tests\test_phase3a_planner.py --basetemp=.agent_work\temp\m22-contract-pytest` → `42 passed, 1 warning`。warning 为既有 Starlette/httpx `TestClient` deprecation，不影响 M22。
- 首次扩大 focused 集合（含 pipeline/database tests）为 `50 passed, 2 failed, 1 warning`；失败是新测试误把兼容汇总 reason 期待为细节 reason（实际 `summarize_score_details()` 成功统一为 `ok`），已修正测试断言，非业务代码失败。
- 首次全量 pytest：`142 passed, 2 skipped, 1 failed, 1 warning`；失败为 `tests/test_m20_schema_index_hygiene.py` 固定期待 193 docs，但 M22 新 metric 实际构建 194 docs，已更新该基线断言后待复跑。其余 142 条通过；warning 为既有 Starlette/httpx deprecation。
- 全量 pytest 复跑：`143 passed, 2 skipped, 1 warning`，耗时 `438.67s`；唯一 warning 为既有 Starlette/httpx `TestClient` deprecation。
- 初次默认 DeepSeek + local deterministic + weighted、`LANGFUSE_ENABLED=false` 的 32 条 diagnostic 为 `26/32`；报告三视图的插入位置随后被发现破坏了 Score Summary Markdown 表格，因此修复布局并添加回归测试后，最终重跑快照为 `25/32`（automated `22/27`，manual `3/5`）。report 为 `eval/reports/m22-default-diagnostic-report.md`，triage 为 `eval/reports/m22-default-diagnostic-triage.json`，trace 为 `eval/traces/m22-default-diagnostic-traces.jsonl`。这是 M22 改动后的口径快照，不能同 M21 `21/32` 直接解释为模型提分。`db_plan_002/003/004` 均结构化通过；`db_prompt_002` 实际 SQL 已采用 SCD overlap 条件。`db_core_004` 仍未在 QueryPlan 中规划排序，下一步补充该题的 QueryPlan prompt 约束；`db_simple_001` 显示 SQL generation 丢了计划中的 products.id ASC，因此被 SQL plan contract 拦截，属于 M22 输出合同发现的真实生成缺口，不扩大到通用列表排序优化。
- `db_core_004` 单 case 默认链路复测（补充排序 QueryPlan 约束后）：`result_match_ok`，SQL 已生成 `ORDER BY order_count DESC, channels.channel_name ASC`；trace 为 `.codex/temp_work/m22-db-core-004-trace.jsonl`。这是 SQLite deterministic oracle 下的回归证据；仍不把一次实时 LLM 成功外推为整个 32 条快照都已刷新。

## 模块名称与改动文件清单

- 模块：M22 Eval Contract / Semantic Output Stabilization。
- 代码与测试：`engine/nl2sql/semantic_validation.py`、`engine/nl2sql/pipeline.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py`、`eval/scorers/rule_scorers.py`、`eval/run_eval.py`、`tests/test_m22_eval_contract.py`、`tests/test_m20_schema_index_hygiene.py`。
- 事实源与用例：`domain_pack/metrics.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`eval/cases/phase3a-regression.yaml`。
- 产物：`eval/reports/m22-default-diagnostic-report.md`、`eval/reports/m22-default-diagnostic-triage.json`、`eval/traces/m22-default-diagnostic-traces.jsonl`（默认 gitignore）、`.codex/temp_work/m22-db-core-004-trace.jsonl`（一次性复测 trace）。`docs/dev-log.md` 和 `docs/state/AI_CONTEXT_CHANGELOG.md` 的已有用户改动不属于 M22，收工时保留并只追加模块档案。

## 阶段 1 注释小结

- 覆盖扫描：M22 新增 `semantic_validation` 类/函数、SQL plan contract、Context / Plan scorer、trace 读取与报告三视图，以及 10 条回归测试均具有中文模块或函数 docstring；0 处缺失。
- 质量扫描：已明确“trace 过程证据不进入 API 响应”“语义拒绝不是 SQL Guard / LLM transport error”“只检查 QueryPlan 已声明的排序 / limit，不能泛化解析 SQL”三项设计边界。
- 内部可读性：`pipeline.py` 为语义预检和只读 SQL 合同顺序补充步骤注释；`rule_scorers.py` 标注专属 contract 必须在输出列检查前执行；`run_eval.py` 标注 scorer 私有 trace 字段不改变 API 契约。
- 形式扫描：新增注释以中文为主，关键边界使用 ★，长流程采用既有步骤分隔线；未发现过时注释或需要额外对齐的格式问题。

## 阶段 2 最终验证快照

- M22 contract / planner focused：`pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_eval.py tests\test_phase3a_planner.py --basetemp=.agent_work\temp\m22-contract-pytest` → `42 passed, 1 warning`。
- M22 pipeline / planner focused：`pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\m22-pipeline-contract-pytest` → `28 passed, 1 warning`。
- 全量 pytest（最终）：`pytest -q --basetemp=.agent_work\temp\m22-full-pytest-report-final` → `144 passed, 2 skipped, 1 warning`，耗时 `407.64s`。
- 默认 diagnostic（报告布局修复后重跑）：32 条 `new_text2sql`、DeepSeek 默认链路、local deterministic、weighted、SQLite deterministic oracle、LangFuse disabled → `25/32`（automated `22/27`；manual `3/5`）；详见上述报告与 triage。M21 `21/32` 是历史快照，两个总分不作模型能力的直接比较。
- 额外 SQL 行为证据：`db_prompt_002` trace 的两次 SQL 均使用 `valid_from < 2026-07-01 AND (valid_to IS NULL OR valid_to > 2026-06-01)` overlap；`db_core_004` 单 case `result_match_ok`。
- warning：仅既有 Starlette/httpx `TestClient` deprecation；Windows LF/CRLF 提示不属于 whitespace error，`git diff --check` 无 whitespace error。

## 参考资料

- 无外部资料。实现依据为 M22 计划、`m22-review-notes.md` 的只读审计、项目既有 trace/scorer/pipeline 代码；未引入 reranker、AST 泛化改写或新的数据库机制。

## 遗留 / 后续

- `db_simple_001` 真实 LLM 仍可能在 SQL generation 丢失已规划的 `products.id ASC`，现在会被 `sql_plan_contract_failed` 结构化暴露；这不是 M22 的核心修复目标，不在本模块扩展成所有列表题的排序策略。
- 由于 `coupon_order_count` 新增 metric document，后续 retrieval benchmark 要使用 194-doc corpus 与新 hash；M21 193-doc A/B 只保留历史事实，不可跨 corpus 直接对比。
- M23 若研究 RRF / rerank，必须以 M22 后 case/scorer 口径重新建立 retrieval-only 和端到端基线；不自动切默认模型、embedding、Milvus 或 fusion。
