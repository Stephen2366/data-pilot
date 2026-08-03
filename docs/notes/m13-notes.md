# M13 Notes - Phase 3A pipeline quality fix

## Checklist

- [x] Step 0: Record staged execution plan in v5 and create this notes file.
- [x] Step 1: Add `expected_value` eval check with failing test first.
- [x] Step 2: Inject metric `filter/default_time_field` into new pipeline prompts.
- [x] Step 2b: Add task-specific system prompt support without breaking fake LLM clients.
- [x] Step 3: Run focused tests, then relevant regression tests.
- [x] Step 4: Re-run formal / challenge / diagnostic new pipeline reports if LLM access is available.
- [x] Step 5: Record residual failures and decide whether trace enhancement or JSON-mode experiment is next.
- [x] Step 6: Fix alias scoring, item_gmv/product/category prompt constraints, conversion-rate float division, and stale category expected text.
- [x] Step 7: Call `finish-module` after the staged work is complete.

## Decisions

- M13 uses staged execution, not one-shot changes, so eval calibration can be separated from prompt fixes.
- `expected_value` is the first code change because current `contains: gmv` can pass when the SQL result is NULL.
- JSON mode remains a hypothesis for later experiment, not a first-batch production change.
- `p3a_multi_002` should not be assumed to be a Schema Retrieval miss until trace proves where `products` dropped out.
- `expected_value` single-metric cases now allow a single actual result column with any alias, then validate by numeric value. This avoids chasing localized aliases like `"2026年6月GMV"` while still rejecting multi-column ambiguous results.
- 一级类目销售额的 current seed top category is `SaaS 软件`, not `数码电子`; formal/challenge category-ranking checks were updated after direct DB verification.

## Verification Log

- RED: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py::test_expected_value_check_fails_when_metric_value_is_null -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-expected-value-red` failed because `_score_case()` returned `ok` for unknown `expected_value`.
- GREEN: same test with `--basetemp=.agent_work/temp/pytest-m13-expected-value-green` passed after adding `_score_expected_value()`.
- Eval focused regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-eval` -> 14 passed, 1 existing Starlette/httpx warning.
- Fixed facts used in YAML: GMV `11285752.00`; net revenue computed from deterministic seed as `11293058.25`.
- Added formal/challenge YAML `expected_value` checks for GMV and net revenue.
- Prompt RED: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py::test_query_plan_prompt_includes_metric_filter_and_default_time_field -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-prompt-red` failed because local metric prompt omitted `orders.paid_at`.
- Prompt GREEN: same test with `--basetemp=.agent_work/temp/pytest-m13-prompt-green` passed after `_format_plan_metrics()` added filter/default time field.
- System prompt RED: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py::test_generator_passes_task_specific_system_prompts -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-system-red` failed because generator passed no task-specific system prompt.
- System prompt GREEN: same test with `--basetemp=.agent_work/temp/pytest-m13-system-green` passed after adding optional system prompt support with fallback for old fake clients.
- Planner focused regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-planner` -> 11 passed.
- Pipeline regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-pipeline` -> 4 passed, 1 existing Starlette/httpx warning.
- M4 regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m4_nl2sql.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-m4` -> 5 passed, 1 existing Starlette/httpx warning.
- Eval regression after pass-path test: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-eval-2` -> 15 passed, 1 existing Starlette/httpx warning.
- Related regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py tests\test_m4_nl2sql.py tests\test_m5_agent_response.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-related` -> 38 passed, 1 existing Starlette/httpx warning.
- Real LLM report check: current shell has `DEEPSEEK_API_KEY_SET=False` and `LLM_API_KEY_SET=False`, so formal/challenge/diagnostic new pipeline reports were not rerun in this pass.
- Full regression before trace enhancement: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-full` -> 69 passed, 2 skipped, 1 existing Starlette/httpx warning.
- Config recheck via `app.core.config.get_settings()`: `.env` has DeepSeek key/base URL and SiliconFlow key; `LLM_PROVIDER=mock` is acceptable because `get_default_llm_client()` uses DeepSeek when key exists.
- Real LLM formal after first-batch fix: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\phase3a-regression.yaml --report eval\reports\phase3a-new-pipeline.md --trace .agent_work\temp\phase3a-new-traces.jsonl` -> first run 6/10; GMV and net revenue both `expected_value_ok`.
- Real LLM challenge: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\database-upgrade-challenge.yaml --report eval\reports\phase3a-challenge-new-pipeline.md --trace .agent_work\temp\phase3a-challenge-new-traces.jsonl` -> 10/16; GMV and net revenue both `expected_value_ok`.
- Real LLM diagnostic: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --report eval\reports\phase3a-diagnostic-new-pipeline.md --trace .agent_work\temp\phase3a-diagnostic-new-traces.jsonl` -> 20/32.
- Comparison reports regenerated: `phase3a-comparison.md`, `phase3a-challenge-comparison.md`, `phase3a-diagnostic-comparison.md`.
- Added trace metadata after residual analysis: `schema_retrieval.metadata.metric_doc_hits`; `sql_generation.metadata.plan_step_tables/columns/filters/metrics/joins/output_columns`.
- Trace RED/GREEN: `tests\test_phase3a_pipeline.py::test_force_new_pipeline_bypasses_template_and_writes_required_trace_steps` failed first on missing `metric_doc_hits`, then on missing `plan_step_tables`; passed after metadata additions.
- Related regression after trace enhancement: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py tests\test_m4_nl2sql.py tests\test_m5_agent_response.py -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-related-2` -> 38 passed, 1 existing warning.
- Full regression after trace enhancement: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m13-full-2` -> 71 passed, 1 existing Starlette/httpx warning.
- Alias-focused eval regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py --basetemp=.agent_work\temp\pytest-m13-alias-2` -> 17 passed, 1 existing warning. A default basetemp run failed only because Windows refused to delete locked `.agent_work/temp/pytest-tmp`.
- QueryPlan item/category prompt RED/GREEN: `tests\test_phase3a_planner.py::test_query_plan_prompt_guides_product_and_category_sales_to_item_gmv` failed on missing `order_items.product_id` guidance, then passed after adding plan notes.
- Active product list prompt RED/GREEN: `tests\test_phase3a_planner.py::test_query_plan_prompt_guides_active_product_list_columns` failed before adding `products.product_name/category/status` guidance, then passed.
- Local SQL item_gmv join RED/GREEN: `tests\test_phase3a_planner.py::test_local_schema_sql_prompt_guides_item_gmv_to_products_join` failed before requiring `order_items.product_id = products.id`, then passed.
- Conversion-rate float division RED/GREEN: `tests\test_phase3a_planner.py::test_local_schema_sql_prompt_guides_conversion_rate_to_float_division` failed before adding `* 1.0` / `CAST(... AS REAL)` guidance, then passed.
- Single-metric expected_value alias RED/GREEN: `tests\test_phase3a_eval.py::test_expected_value_check_accepts_single_metric_column_alias` failed on `missing_columns=['gmv']`, then passed after scorer fallback.
- Related regression after second-batch prompt/scorer fixes: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-single-metric-related` -> 37 passed, 1 existing warning.
- Real LLM formal after second-batch fixes: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\phase3a-regression.yaml --report eval\reports\phase3a-new-pipeline.md --trace .agent_work\temp\phase3a-new-traces.jsonl` -> 10/10.
- Real LLM challenge after second-batch fixes: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\database-upgrade-challenge.yaml --report eval\reports\phase3a-challenge-new-pipeline.md --trace .agent_work\temp\phase3a-challenge-new-traces.jsonl` -> 14/16.
- Real LLM diagnostic after second-batch fixes: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --report eval\reports\phase3a-diagnostic-new-pipeline.md --trace .agent_work\temp\phase3a-diagnostic-new-traces.jsonl` -> 23/32, review_required=3.
- Full regression final: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest --basetemp=.agent_work\temp\pytest-m13-final-full-2` -> 78 passed, 1 existing Starlette/httpx warning.
- `git diff --check` -> no whitespace errors, only Windows CRLF warnings.
- Formal/challenge comparison reports regenerated with latest traces: `eval/reports/phase3a-comparison.md`, `eval/reports/phase3a-challenge-comparison.md`.
- Diagnostic comparison report regenerated with latest trace: `eval/reports/phase3a-diagnostic-comparison.md`.
- finish-module 注释补强：`eval/run_eval.py` 补单指标数值兜底注释；`engine/nl2sql/prompt.py` 补 item_gmv 计划约束注释。
- finish-module related regression: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-finish-related` -> 37 passed, 1 existing Starlette/httpx warning.

## Residual Failure Notes

- `paid_at` / `unpaid` / NULL class is fixed for GMV and net revenue: real LLM reports now pass via `expected_value_ok`.
- Formal regression latest is 10/10.
- Challenge latest is 14/16. Remaining failures: `db_multi_002` hit an LLM generation error in that run; `db_hard_001` is a non-blocking manual-review recursive category case blocked by SQL Guard.
- Diagnostic latest is 23/32. Remaining failures: 5 missing-column style diagnostic failures (`db_schema_002`, `db_join_002`, `db_prompt_001`, `db_prompt_002`, `db_prompt_003`), 2 plan/guard blocked diagnosis cases (`db_join_003`, `db_plan_003`), 1 non-blocking recursive category SQL Guard block (`db_hard_001`), and 1 security diagnostic miss (`db_sec_004` safety_mismatch).
