# M21 Qwen-plus 本地 vs Qwen embedding 对照

## 目标

- 固定主模型为 `qwen3.7-plus`，只改变 Schema Retrieval backend / embedding：
  - A：`inmemory + deterministic`
  - B：clean Milvus + DashScope `qwen3.7-text-embedding`
- 两组都使用 weighted fusion、同一 diagnostic 32 题、同一 pipeline mode、同一 oracle 和 `LANGFUSE_ENABLED=false`。

## 执行清单

- [x] A 组完整 diagnostic：Qwen-plus + inmemory/deterministic + weighted，`21/32`
  - failure_stage：`schema_context=6`、`schema_retrieval=2`、`sql_generation=2`、`result_match=1`、`unknown=2`
  - failure_subtype：`output_column_contract=6`、`output_table_contract=2`、`result_contract=1`
  - report：`.agent_work/temp/m21-qwen-plus-local-weighted-report.md`
  - triage：`.agent_work/temp/m21-qwen-plus-local-weighted-triage.json`
- [x] B 组完整 diagnostic：Qwen-plus + clean Milvus/Qwen embedding + weighted，`21/32`
  - collection：`datapilot_schema_docs_m21_qwen_weighted_20260803_001`
  - metadata：`milvus_final_row_count=193`、schema hash 一致、`schema_vector_index_reuse=run_scoped`
  - failure_stage：`schema_context=6`、`schema_retrieval=2`、`query_plan=1`、`result_match=1`、`sql_generation=1`、`unknown=1`
  - failure_subtype：`output_column_contract=6`、`output_table_contract=2`、`result_contract=1`
  - report：`.agent_work/temp/m21-qwen-plus-qwenemb-weighted-report.md`
  - triage：`.agent_work/temp/m21-qwen-plus-qwenemb-weighted-triage.json`
- [x] 对比总分、failure_stage、failure_subtype、timeout 和运行元数据
  - triage compare：`.agent_work/temp/m21-qwen-plus-local-vs-qwenemb-triage-compare.md`
  - 两组均为 `21/32`；`schema_context` 和全部 failure_subtype 数量完全相同。
  - case-level 只有 3 个失败形态变化：`db_hard_001`（schema_retrieval → query_plan）、`db_join_003`（unknown → schema_retrieval）、`db_plan_004`（失败 → 通过）。
- [x] 不切默认模型、embedding、Milvus 或 fusion

## 结论

- 这次严格单变量 A/B 没有显示 Qwen embedding 带来端到端提分：两组都是 `21/32`。
- `schema_context` 和 `failure_subtype` 分布不变；阶段变化属于少数 case 的 LLM 运行波动/失败转移，不能作为 embedding 优势证据。
- M21 embedding 线到此收口；下一步转 M22，优先处理 output contract 和 QueryPlan → SQL 稳定性。

## 预设口径

- Schema docs count：193
- Schema docs hash：`7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`
- B 组 collection：`datapilot_schema_docs_m21_qwen_weighted_20260803_001`
- 结束条件：只判断 embedding 是否在相同 Qwen-plus 条件下带来可解释的端到端 / subtype 变化；若没有，转 M22，不继续堆 embedding 参数。
