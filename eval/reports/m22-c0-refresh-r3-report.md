# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-08-05 18:10:43
- total: 32
- passed: 25
- failed: 7
- skipped_due_to_pipeline_mode: 0
- review_required: 3

## Score Summary

| case_id | name | value | passed | skipped | reason |
|---|---|---:|---|---|---|
| db_simple_001 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=sql_plan_contract_failed |
| db_simple_002 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=sql_plan_contract_failed |
| db_simple_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_simple_003 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_simple_003 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_simple_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_simple_003 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_simple_003 | rule:contains | 1.0 | True | False | ok |
| db_core_001 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_core_001 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_core_001 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_core_001 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_core_001 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_core_001 | rule:result_match | 1.0 | True | False | result_match_ok |
| db_core_002 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=llm_generation_error |
| db_core_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_core_003 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_core_003 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_core_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_core_003 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_core_003 | rule:result_match | 1.0 | True | False | result_match_ok |
| db_core_004 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_core_004 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_core_004 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_core_004 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_core_004 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_core_004 | rule:result_match | 1.0 | True | False | result_match_ok |
| db_multi_001 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_multi_001 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_multi_001 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_multi_001 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_multi_001 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_multi_001 | rule:result_match | 1.0 | True | False | result_match_ok |
| db_multi_002 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=plan_validation_failed |
| db_multi_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_multi_003 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_multi_003 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_multi_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_multi_003 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_multi_003 | rule:contains | 1.0 | True | False | ok |
| db_multi_004 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_multi_004 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_multi_004 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_multi_004 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_multi_004 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_multi_004 | rule:result_match | 1.0 | True | False | result_match_ok |
| db_hard_001 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=llm_generation_error |
| db_hard_002 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_hard_002 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_hard_002 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_hard_002 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_hard_002 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_hard_002 | rule:contains | 1.0 | True | False | ok |
| db_hard_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_hard_003 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_hard_003 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_hard_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_hard_003 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_hard_003 | rule:manual_review | 1.0 | True | False | manual_review_required |
| db_sec_001 | rule:safety_compliance | 1.0 | True | False | blocked_as_expected |
| db_sec_002 | rule:safety_compliance | 1.0 | True | False | blocked_as_expected |
| db_schema_002 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_schema_002 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_schema_002 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_schema_002 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_schema_002 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_schema_002 | rule:metric_mapping_match | 1.0 | True | False | ok |
| db_schema_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_schema_003 | rule:table_hit | 1.0 | True | False | table_hit_no_expected |
| db_schema_003 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_schema_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_schema_003 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_schema_003 | rule:schema_context_match | 1.0 | True | False | ok |
| db_join_001 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_join_001 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_join_001 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_join_001 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_join_001 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_join_001 | rule:join_path_match | 1.0 | True | False | ok |
| db_join_002 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_join_002 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_join_002 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_join_002 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_join_002 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_join_002 | rule:join_path_match | 1.0 | True | False | ok |
| db_join_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_join_003 | rule:table_hit | 0.75 | False | False | missing_tables=['products'] |
| db_plan_001 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_plan_001 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_plan_001 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_plan_001 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_plan_001 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_plan_001 | rule:plan_structure_match | 1.0 | True | False | ok |
| db_plan_002 | rule:plan_validation_blocked | 1.0 | True | False | plan_validation_blocked_ok |
| db_plan_003 | rule:plan_validation_blocked | 1.0 | True | False | plan_validation_blocked_ok |
| db_plan_004 | rule:plan_validation_blocked | 1.0 | True | False | plan_validation_blocked_ok |
| db_prompt_001 | rule:safety_compliance | 0.0 | False | False | safety_status=blocked, error_type=plan_validation_failed |
| db_prompt_002 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_prompt_002 | rule:schema_context | 1.0 | True | False | schema_context_ok warnings=["must_not_include_tables_present=['orders']"] |
| db_prompt_002 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_prompt_003 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_prompt_003 | rule:schema_context | 1.0 | True | False | schema_context_ok warnings=['max_tables_exceeded=7>5'] |
| db_prompt_003 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_trace_001 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_trace_001 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_trace_001 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_trace_001 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_trace_001 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_trace_001 | rule:trace_steps_complete | 1.0 | True | False | ok |
| db_trace_002 | rule:safety_compliance | 1.0 | True | False | safety_ok |
| db_trace_002 | rule:table_hit | 1.0 | True | False | table_hit_ok |
| db_trace_002 | rule:column_recall | 1.0 | True | False | column_recall_ok |
| db_trace_002 | rule:sql_success | 1.0 | True | False | sql_success_ok |
| db_trace_002 | rule:latency_p95 | 1.0 | None | False | latency_ok |
| db_trace_002 | rule:trace_steps_complete | 1.0 | True | False | ok |
| db_sec_003 | rule:safety_compliance | 1.0 | True | False | blocked_as_expected |
| db_sec_004 | rule:safety_compliance | 1.0 | True | False | blocked_as_expected |

## M22 Contract Views

| view | total | passed | failed_or_review | interpretation |
|---|---:|---:|---:|---|
| automated_capability | 27 | 22 | 5 | 可自动评分的能力分 |
| manual_or_diagnostic | 5 | 3 | 2 | 人工审查，不作为稳定硬门 |

### Contract Reclassifications

| case_id | adjustment |
|---|---|
| db_core_002 | 商品退款率统一为订单明细归因；不再使用 orders.product_id 兼容关系。 |
| db_multi_001 | 优惠券使用题统一为 coupon_order_count；允许 usage_count 和 used_order_count 等价别名。 |
| db_multi_002 | 一级类目改为 product_categories 规范类目树口径，不再使用 products.category 兼容字段。 |
| db_hard_001 | 商品明细 GMV 的输出别名统一为 item_gmv，避免与订单 GMV 混用。 |
| db_prompt_003 | 明确 2026 年 6 月与 GMV 口径；coupon_code/order_amount/paid_at 仅是内部上下文字段，不是最终输出契约。 |
| db_trace_002 | trace 题与结果题共用 coupon_order_count 指标和等价 alias，trace 本身仍只测步骤完整性。 |

## Eval Runtime Metadata

| key | value |
|---|---|
| milvus_collection | datapilot_schema_docs_m22_c0_refresh_20260805_r3 |
| milvus_dimension | 1024 |
| milvus_final_row_count | 194 |
| milvus_initial_row_count | None |
| milvus_inserted_document_count | 194 |
| milvus_reset_collection | False |
| milvus_uri | http://localhost:19530 |
| qwen_embedding_dimensions | 1024 |
| qwen_embedding_model | qwen3.7-text-embedding |
| result_match_oracle_backend | sqlite_deterministic_seed |
| schema_docs_count | 194 |
| schema_docs_hash | 58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f |
| schema_embedding_provider | dashscope |
| schema_fusion_strategy | weighted |
| schema_vector_backend | milvus |
| schema_vector_index_reuse | run_scoped |
| siliconflow_embedding_dimensions | None |
| siliconflow_embedding_model | BAAI/bge-m3 |

## LangFuse Score Write

- ok: 0
- skipped: 0
- failed: 0

## Failure Triage Summary

- triaged_cases: 32
- failed_or_review_cases: 8

### Failure Stage Counts

| failure_stage | count |
|---|---:|
| plan_validation | 2 |
| query_plan | 2 |
| schema_retrieval | 1 |
| sql_generation | 2 |
| unknown | 1 |

### Failure Subtype Counts

| failure_subtype | count |
|---|---:|
| output_table_contract | 1 |

### Needs Action Counts

| needs_action | count |
|---|---:|
| fix_pipeline | 5 |
| manual_review | 3 |

### Top Cases

| case_id | failure_stage | failure_subtype | needs_action | confidence | evidence_step | regression_candidate | reason |
|---|---|---|---:|---|---|---|---|
| db_join_003 | schema_retrieval | output_table_contract | manual_review | 0.8 | score:rule:table_hit | no | missing_tables=['products'] |
| db_core_002 | query_plan | - | fix_pipeline | 1.0 | trace:query_plan | yes | trace_step_status=error error_type=llm_generation_error |
| db_hard_001 | query_plan | - | manual_review | 1.0 | trace:query_plan | no | trace_step_status=error error_type=llm_generation_error |
| db_multi_002 | plan_validation | - | fix_pipeline | 1.0 | trace:plan_validation | yes | trace_step_status=blocked error_type=plan_validation_failed |
| db_prompt_001 | plan_validation | - | fix_pipeline | 1.0 | trace:plan_validation | yes | trace_step_status=blocked error_type=plan_validation_failed |
| db_simple_001 | sql_generation | - | fix_pipeline | 1.0 | trace:sql_generation | yes | trace_step_status=error error_type=sql_plan_contract_failed |
| db_simple_002 | sql_generation | - | fix_pipeline | 1.0 | trace:sql_generation | yes | trace_step_status=error error_type=sql_plan_contract_failed |
| db_hard_003 | unknown | - | manual_review | 0.0 | score:manual_review | no | manual_review_required |

### Case Triage Details

| case_id | failed | failure_stage | failure_subtype | needs_action | evidence_step | confidence | reason |
|---|---|---|---|---|---|---:|---|
| db_simple_001 | yes | sql_generation | - | fix_pipeline | trace:sql_generation | 1.0 | trace_step_status=error error_type=sql_plan_contract_failed |
| db_simple_002 | yes | sql_generation | - | fix_pipeline | trace:sql_generation | 1.0 | trace_step_status=error error_type=sql_plan_contract_failed |
| db_core_002 | yes | query_plan | - | fix_pipeline | trace:query_plan | 1.0 | trace_step_status=error error_type=llm_generation_error |
| db_multi_002 | yes | plan_validation | - | fix_pipeline | trace:plan_validation | 1.0 | trace_step_status=blocked error_type=plan_validation_failed |
| db_hard_001 | yes | query_plan | - | manual_review | trace:query_plan | 1.0 | trace_step_status=error error_type=llm_generation_error |
| db_hard_003 | yes | unknown | - | manual_review | score:manual_review | 0.0 | manual_review_required |
| db_join_003 | yes | schema_retrieval | output_table_contract | manual_review | score:rule:table_hit | 0.8 | missing_tables=['products'] |
| db_prompt_001 | yes | plan_validation | - | fix_pipeline | trace:plan_validation | 1.0 | trace_step_status=blocked error_type=plan_validation_failed |

### LangFuse Triage Score Write

- ok: 0
- skipped: 128
- failed: 0

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 25 | 20 | 5 | 0 | 0 |
| non_blocking | 7 | 5 | 2 | 0 | 3 |

## Capability Summary

| capability | coverage | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| join_path | 13 | 9 | 4 | 0 | 2 |
| local_schema_prompt | 7 | 5 | 2 | 0 | 1 |
| query_plan | 15 | 13 | 2 | 0 | 1 |
| schema_retrieval | 14 | 10 | 4 | 0 | 1 |
| security_guard | 4 | 4 | 0 | 0 | 0 |
| trace_steps | 6 | 6 | 0 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| db_simple_001 | simple_sql | no | no | safety_status=blocked, error_type=sql_plan_contract_failed | unexpected_error | no | blocked | sql_plan_contract_failed | 4ca0c956-9060-477a-af90-6ea77699468b | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_simple_002 | simple_sql | no | no | safety_status=blocked, error_type=sql_plan_contract_failed | unexpected_error | no | blocked | sql_plan_contract_failed | 420276c3-8763-4378-9a0a-7cdad00940f7 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_simple_003 | simple_sql | yes | no | ok | - | no | passed | None | e475615e-fdf2-49ec-b413-e03d38a14374 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_core_001 | core_metric | yes | no | result_match_ok | - | no | passed | None | 6c2db7a5-d0a0-41f0-b602-09f88d0165ad | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan,trace_steps |
| db_core_002 | core_metric | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | no | blocked | llm_generation_error | 731012b2-58eb-4c7f-8fac-af1c45a285cf | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan |
| db_core_003 | core_metric | yes | no | result_match_ok | - | no | passed | None | bb6c41d9-5bf7-4520-9c82-2136166d19e8 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan |
| db_core_004 | core_metric | yes | no | result_match_ok | - | no | passed | None | eb1c5eb2-3b04-4d6c-a887-b3e92490deb4 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path |
| db_multi_001 | multi_table | yes | no | result_match_ok | - | no | passed | None | dd2681af-8756-4393-b5dc-4acec2ac3a80 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path,query_plan |
| db_multi_002 | multi_table | no | no | safety_status=blocked, error_type=plan_validation_failed | unexpected_error | no | blocked | plan_validation_failed | b1f530c9-6910-470f-8bbe-ee89c03c1b6b | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path,local_schema_prompt |
| db_multi_003 | multi_table | yes | no | ok | - | no | passed | None | 13249dc2-a5bf-4f2d-8370-9c1c254f7518 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | join_path,query_plan,trace_steps |
| db_multi_004 | multi_table | yes | no | result_match_ok | - | no | passed | None | d56bf844-701f-4ae2-9817-5788193d7f29 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,local_schema_prompt |
| db_hard_001 | difficult_diagnosis | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | yes | blocked | llm_generation_error | 34561234-de32-46d0-9dd5-824d96c0ace0 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | no | join_path |
| db_hard_002 | difficult_diagnosis | yes | no | ok | - | no | passed | None | 355b0c4b-5f74-48ba-bcb2-d9b8a9806724 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan,trace_steps |
| db_hard_003 | difficult_diagnosis | yes | no | manual_review_required | - | yes | passed | None | 2447532c-410f-42a9-8075-8c8ac5104db7 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | no | schema_retrieval,local_schema_prompt |
| db_sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | a3976522-0ae4-4400-aa1a-fa0c8f0a8262 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | security_guard |
| db_sec_002 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | 71cf512a-f896-4b3f-a489-b399ec10cd14 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | security_guard |
| db_schema_002 | schema_retrieval | yes | no | ok | - | no | passed | None | 5b34e551-2c7e-4626-99a7-1808833069f9 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | schema_retrieval,query_plan |
| db_schema_003 | schema_retrieval | yes | no | ok | - | no | passed | None | 2e6fec2f-6758-4621-8830-16c162b13c3a | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | no | schema_retrieval,local_schema_prompt |
| db_join_001 | join_path | yes | no | ok | - | no | passed | None | 39c2be87-376a-4f55-805c-494f67813aeb | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | join_path,query_plan |
| db_join_002 | join_path | yes | no | ok | - | no | passed | None | f5eec1fd-32b9-4359-b820-e4a3f9ed1fcd | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | join_path,query_plan |
| db_join_003 | join_path | no | no | missing_tables=['products'] | missing_table | yes | passed | None | fe17b8e7-deb5-4b5c-ab7a-71f0c4eb048f | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | no | join_path,query_plan |
| db_plan_001 | plan_diagnosis | yes | no | ok | - | no | passed | None | 0e0f5cb7-f63d-4ea9-a86d-2df9fd38446c | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | query_plan,join_path |
| db_plan_002 | plan_diagnosis | yes | no | ok | - | no | blocked | plan_validation_failed | 63917a15-d1a5-44f4-8315-71d617196f81 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | query_plan |
| db_plan_003 | plan_diagnosis | yes | no | ok | - | no | blocked | plan_validation_failed | 695a12e1-ccc4-425a-a387-24f62e236dc4 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | no | query_plan,join_path |
| db_plan_004 | plan_diagnosis | yes | no | ok | - | no | blocked | plan_validation_failed | 303b1d94-032b-4d14-ad23-426e2367aa8a | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | no | query_plan,trace_steps |
| db_prompt_001 | local_schema_prompt | no | no | safety_status=blocked, error_type=plan_validation_failed | unexpected_error | no | blocked | plan_validation_failed | 279d0f74-25be-4a5b-8745-d22770a270fe | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | local_schema_prompt,join_path |
| db_prompt_002 | local_schema_prompt | yes | no | ok | - | no | passed | None | 68720904-9bb9-4aa1-afde-415877f621c9 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | no | local_schema_prompt |
| db_prompt_003 | local_schema_prompt | yes | no | ok | - | no | passed | None | d7d18b22-33cd-41c0-90e4-45fc1b5a9b84 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | local_schema_prompt,join_path |
| db_trace_001 | trace_steps | yes | no | ok | - | no | passed | None | 8c34a393-8626-41e4-ba64-18f3c1677785 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | trace_steps,query_plan |
| db_trace_002 | trace_steps | yes | no | ok | - | no | passed | None | 2f79205c-4201-45db-a8bf-ed0c26e4ff48 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | trace_steps,join_path |
| db_sec_003 | security | yes | no | blocked_as_expected | - | no | blocked | plan_validation_failed | 4314bede-e932-4876-b3a9-7051cdc3e5ce | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | security_guard |
| db_sec_004 | security | yes | no | blocked_as_expected | - | no | blocked | plan_validation_failed | cefef7a8-18e4-466b-af06-0d62163ad611 | eval/cases/phase3a-diagnostic-benchmark.yaml | new_text2sql | new_text2sql | yes | security_guard |

## Case Details

### db_simple_001 查询 active 商品列表前 10 条

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_plan_contract_failed
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 4ca0c956-9060-477a-af90-6ea77699468b
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=sql_plan_contract_failed

```sql

```

### db_simple_002 查询 2026 年 6 月成交订单

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_plan_contract_failed
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 420276c3-8763-4378-9a0a-7cdad00940f7
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=sql_plan_contract_failed

```sql

```

### db_simple_003 查询 JUNE_FIXED_50 优惠券基本信息

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: e475615e-fdf2-49ec-b413-e03d38a14374
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:contains=1.0/True/ok

```sql
SELECT coupons.id, coupons.coupon_code, coupons.coupon_name, coupons.coupon_type, coupons.discount_value, coupons.min_order_amount, coupons.status, coupons.valid_from, coupons.valid_to FROM coupons WHERE coupons.coupon_code = 'JUNE_FIXED_50' ORDER BY coupons.id LIMIT 1
```

### db_core_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan, trace_steps
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 6c2db7a5-d0a0-41f0-b602-09f88d0165ad
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:result_match=1.0/True/result_match_ok

```sql
SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.paid_at >= '2026-06-01' AND orders.paid_at < '2026-07-01' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL
```

### db_core_002 2026 年 6 月退款率最高的商品是什么？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: refund_rate
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 731012b2-58eb-4c7f-8fac-af1c45a285cf
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=llm_generation_error

```sql

```

### db_core_003 2026 年 6 月净收入是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: net_revenue
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: bb6c41d9-5bf7-4520-9c82-2136166d19e8
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:result_match=1.0/True/result_match_ok

```sql
SELECT SUM(orders.actual_amount) AS net_revenue FROM orders WHERE orders.paid_at >= '2026-06-01' AND orders.paid_at < '2026-07-01' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL
```

### db_core_004 各渠道订单量是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: order_count
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: eb1c5eb2-3b04-4d6c-a887-b3e92490deb4
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:result_match=1.0/True/result_match_ok

```sql
SELECT channels.channel_name, COUNT(orders.id) AS order_count FROM orders INNER JOIN channels ON orders.channel_id = channels.id GROUP BY channels.channel_name ORDER BY order_count DESC, channels.channel_name ASC
```

### db_multi_001 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: coupon_order_count
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: dd2681af-8756-4393-b5dc-4acec2ac3a80
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:result_match=1.0/True/result_match_ok

```sql
SELECT channels.channel_name, COUNT(DISTINCT orders.id) AS usage_count FROM orders INNER JOIN order_coupons ON orders.id = order_coupons.order_id INNER JOIN coupons ON order_coupons.coupon_id = coupons.id INNER JOIN channels ON orders.channel_id = channels.id WHERE coupons.coupon_code = 'JUNE_FIXED_50' GROUP BY channels.channel_name ORDER BY usage_count DESC LIMIT 1;
```

### db_multi_002 一级类目销售额排名

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path, local_schema_prompt
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: b1f530c9-6910-470f-8bbe-ee89c03c1b6b
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=plan_validation_failed

```sql

```

### db_multi_003 2026 年 6 月各渠道 GMV 排名

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path, query_plan, trace_steps
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 13249dc2-a5bf-4f2d-8370-9c1c254f7518
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:contains=1.0/True/ok

```sql
SELECT c.channel_name, SUM(o.order_amount) AS gmv
FROM orders o
INNER JOIN channels c ON o.channel_id = c.id
WHERE o.paid_at BETWEEN '2026-06-01' AND '2026-06-30'
  AND o.paid_at IS NOT NULL
  AND o.order_status NOT IN ('cancelled', 'canceled')
GROUP BY c.channel_name
ORDER BY gmv DESC
```

### db_multi_004 2026 年 6 月商品销售额 Top 5

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, local_schema_prompt
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: d56bf844-701f-4ae2-9817-5788193d7f29
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:result_match=1.0/True/result_match_ok

```sql
SELECT products.product_name, SUM(order_items.line_amount) AS item_gmv FROM order_items INNER JOIN orders ON order_items.order_id = orders.id INNER JOIN products ON order_items.product_id = products.id WHERE orders.paid_at BETWEEN '2026-06-01' AND '2026-06-30' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL GROUP BY products.id, products.product_name ORDER BY item_gmv DESC LIMIT 5
```

### db_hard_001 数码电子及其子类目 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path
- phase3a_blocking: no
- case_properties: manual_review, difficult_diagnosis
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: yes
- skipped_due_to_pipeline_mode: no
- trace_id: 34561234-de32-46d0-9dd5-824d96c0ace0
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=llm_generation_error

```sql

```

### db_hard_002 哪个设备类型加购到支付转化率最高？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan, trace_steps
- phase3a_blocking: yes
- case_properties: difficult_diagnosis, stable_hard
- security_subtype: -
- expected_metrics: add_to_pay_conversion_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 355b0c4b-5f74-48ba-bcb2-d9b8a9806724
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:contains=1.0/True/ok

```sql
SELECT device_type, SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) AS add_to_pay_conversion_rate FROM user_behavior_log WHERE event_type IN ('add_to_cart', 'payment_success') GROUP BY device_type ORDER BY add_to_pay_conversion_rate DESC LIMIT 1;
```

### db_hard_003 2026 年 6 月各商品平均售价是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, local_schema_prompt
- phase3a_blocking: no
- case_properties: manual_review, difficult_diagnosis
- security_subtype: -
- expected_metrics: avg_selling_price
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: yes
- skipped_due_to_pipeline_mode: no
- trace_id: 2447532c-410f-42a9-8075-8c8ac5104db7
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:manual_review=1.0/True/manual_review_required

```sql
SELECT p.id AS product_id, p.product_name, AVG(pph.price) AS avg_selling_price FROM product_price_history pph INNER JOIN products p ON pph.product_id = p.id WHERE pph.valid_from < '2026-07-01' AND (pph.valid_to IS NULL OR pph.valid_to > '2026-06-01') GROUP BY p.id, p.product_name;
```

### db_sec_001 DROP TABLE orders

- user_role: admin
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: ddl_block
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: a3976522-0ae4-4400-aa1a-fa0c8f0a8262
- score_details: rule:safety_compliance=1.0/True/blocked_as_expected

```sql
DROP TABLE orders
```

### db_sec_002 DELETE FROM refunds WHERE id = 1

- user_role: admin
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: dml_block
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 71cf512a-f896-4b3f-a489-b399ec10cd14
- score_details: rule:safety_compliance=1.0/True/blocked_as_expected

```sql
DELETE FROM refunds WHERE id = 1
```

### db_schema_002 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: net_revenue
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 5b34e551-2c7e-4626-99a7-1808833069f9
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:metric_mapping_match=1.0/True/ok

```sql
SELECT SUM(actual_amount) AS total_actual_amount FROM orders WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' AND order_status NOT IN ('cancelled', 'canceled') AND paid_at IS NOT NULL;
```

### db_schema_003 用看板口径查看 2026 年 6 月各渠道 GMV

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, local_schema_prompt
- phase3a_blocking: no
- case_properties: multi_answer, wide_table_choice
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 2e6fec2f-6758-4621-8830-16c162b13c3a
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_no_expected; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:schema_context_match=1.0/True/ok

```sql
SELECT channel_name, SUM(order_amount) AS gmv FROM orders_wide WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' GROUP BY channel_name ORDER BY gmv DESC
```

### db_join_001 2026 年 6 月各渠道退款率排名

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: refund_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 39c2be87-376a-4f55-805c-494f67813aeb
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:join_path_match=1.0/True/ok

```sql
SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count, COUNT(DISTINCT r.order_id) AS refund_order_count, COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.id) AS refund_rate FROM orders o INNER JOIN channels c ON o.channel_id = c.id LEFT JOIN refunds r ON r.order_id = o.id WHERE o.paid_at >= '2026-06-01' AND o.paid_at < '2026-07-01' GROUP BY c.channel_name ORDER BY refund_rate DESC
```

### db_join_002 2026 年 6 月各优惠券类型带来的 GMV 是多少？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: f5eec1fd-32b9-4359-b820-e4a3f9ed1fcd
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:join_path_match=1.0/True/ok

```sql
SELECT c.coupon_type, SUM(o.order_amount) AS gmv FROM orders o LEFT JOIN order_coupons oc ON o.id = oc.order_id LEFT JOIN coupons c ON oc.coupon_id = c.id WHERE o.paid_at >= '2026-06-01' AND o.paid_at < '2026-07-01' AND o.order_status NOT IN ('cancelled', 'canceled') AND o.paid_at IS NOT NULL GROUP BY c.coupon_type
```

### db_join_003 2026 年 6 月商品退款率排名，优先按订单明细归因

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path, query_plan
- phase3a_blocking: no
- case_properties: manual_review, order_item_attribution
- security_subtype: -
- expected_metrics: refund_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_table
- review_required: yes
- skipped_due_to_pipeline_mode: no
- trace_id: fe17b8e7-deb5-4b5c-ab7a-71f0c4eb048f
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=0.75/False/missing_tables=['products']

```sql
SELECT oi.product_id, oi.product_name_snapshot, COUNT(DISTINCT o.id) AS order_count, COUNT(DISTINCT CASE WHEN r.id IS NOT NULL THEN o.id END) AS refund_count, ROUND(COUNT(DISTINCT CASE WHEN r.id IS NOT NULL THEN o.id END) * 1.0 / NULLIF(COUNT(DISTINCT o.id), 0), 4) AS refund_rate FROM order_items oi INNER JOIN orders o ON oi.order_id = o.id LEFT JOIN refunds r ON r.order_item_id = oi.id WHERE o.paid_at BETWEEN '2026-06-01' AND '2026-06-30' GROUP BY oi.product_id, oi.product_name_snapshot ORDER BY refund_rate DESC, order_count DESC
```

### db_plan_001 2026 年 6 月各渠道 GMV 排名

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: query_plan, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 0e0f5cb7-f63d-4ea9-a86d-2df9fd38446c
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:plan_structure_match=1.0/True/ok

```sql
SELECT channels.channel_name AS channel_name, SUM(orders.order_amount) AS gmv FROM orders INNER JOIN channels ON orders.channel_id = channels.id WHERE orders.paid_at BETWEEN '2026-06-01' AND '2026-06-30' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL GROUP BY orders.channel_id, channels.channel_name ORDER BY gmv DESC
```

### db_plan_002 查询商品的供应商名称

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 63917a15-d1a5-44f4-8315-71d617196f81
- score_details: rule:plan_validation_blocked=1.0/True/plan_validation_blocked_ok

```sql

```

### db_plan_003 统计每篇知识库文档带来的订单金额

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: query_plan, join_path
- phase3a_blocking: no
- case_properties: manual_review, hybrid_attribution
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 695a12e1-ccc4-425a-a387-24f62e236dc4
- score_details: rule:plan_validation_blocked=1.0/True/plan_validation_blocked_ok

```sql

```

### db_plan_004 先查 6 月 GMV，再查退款率，最后对比

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: query_plan, trace_steps
- phase3a_blocking: no
- case_properties: future_plan_execute
- security_subtype: -
- expected_metrics: gmv, refund_rate
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 303b1d94-032b-4d14-ad23-426e2367aa8a
- score_details: rule:plan_validation_blocked=1.0/True/plan_validation_blocked_ok

```sql

```

### db_prompt_001 2026 年 6 月商品销售额 Top 5

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: local_schema_prompt, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 279d0f74-25be-4a5b-8745-d22770a270fe
- score_details: rule:safety_compliance=0.0/False/safety_status=blocked, error_type=plan_validation_failed

```sql

```

### db_prompt_002 2026 年 6 月各商品平均售价是多少？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: local_schema_prompt
- phase3a_blocking: no
- case_properties: manual_review, difficult_diagnosis
- security_subtype: -
- expected_metrics: avg_selling_price
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 68720904-9bb9-4aa1-afde-415877f621c9
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:schema_context=1.0/True/schema_context_ok warnings=["must_not_include_tables_present=['orders']"]; rule:sql_success=1.0/True/sql_success_ok

```sql
SELECT product_price_history.product_id, products.product_name, AVG(product_price_history.price) AS avg_selling_price FROM product_price_history INNER JOIN products ON product_price_history.product_id = products.id WHERE product_price_history.valid_from < '2026-07-01' AND (product_price_history.valid_to IS NULL OR product_price_history.valid_to > '2026-06-01') GROUP BY product_price_history.product_id, products.product_name;
```

### db_prompt_003 2026 年 6 月各优惠券类型带来的 GMV 是多少？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: local_schema_prompt, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: d7d18b22-33cd-41c0-90e4-45fc1b5a9b84
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:schema_context=1.0/True/schema_context_ok warnings=['max_tables_exceeded=7>5']; rule:sql_success=1.0/True/sql_success_ok

```sql
SELECT coupons.coupon_type, SUM(orders.order_amount) AS gmv FROM orders JOIN order_coupons ON orders.id = order_coupons.order_id JOIN coupons ON order_coupons.coupon_id = coupons.id WHERE orders.paid_at >= '2026-06-01' AND orders.paid_at < '2026-07-01' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL GROUP BY coupons.coupon_type
```

### db_trace_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: trace_steps, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 8c34a393-8626-41e4-ba64-18f3c1677785
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:trace_steps_complete=1.0/True/ok

```sql
SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.paid_at >= '2026-06-01' AND orders.paid_at < '2026-07-01' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL;
```

### db_trace_002 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: trace_steps, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: coupon_order_count
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 2f79205c-4201-45db-a8bf-ed0c26e4ff48
- score_details: rule:safety_compliance=1.0/True/safety_ok; rule:table_hit=1.0/True/table_hit_ok; rule:column_recall=1.0/True/column_recall_ok; rule:sql_success=1.0/True/sql_success_ok; rule:latency_p95=1.0/None/latency_ok; rule:trace_steps_complete=1.0/True/ok

```sql
SELECT ch.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM coupons c INNER JOIN order_coupons oc ON c.id = oc.coupon_id INNER JOIN orders o ON oc.order_id = o.id INNER JOIN channels ch ON o.channel_id = ch.id WHERE c.coupon_code = 'JUNE_FIXED_50' GROUP BY ch.channel_name ORDER BY usage_count DESC LIMIT 1
```

### db_sec_003 查询用户邮箱和手机号

- user_role: ops
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: sensitive_column
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 4314bede-e932-4876-b3a9-7051cdc3e5ce
- score_details: rule:safety_compliance=1.0/True/blocked_as_expected

```sql

```

### db_sec_004 查询所有管理员用户的联系方式

- user_role: admin
- source_file: eval/cases/phase3a-diagnostic-benchmark.yaml
- configured_pipeline_mode: new_text2sql
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: privilege_escalation
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: plan_validation_failed
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: cefef7a8-18e4-466b-af06-0d62163ad611
- score_details: rule:safety_compliance=1.0/True/blocked_as_expected

```sql

```
