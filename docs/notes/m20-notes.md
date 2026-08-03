# M20 Schema Retrieval / Milvus Index Hygiene Notes

## Module Name And Changed Files

- Module: M20 Schema Retrieval / Milvus Index Hygiene.
- No module start commit was provided; this finish pass uses current worktree changes.
- Changed files:
  - `app/api/query.py`
  - `engine/nl2sql/pipeline.py`
  - `engine/schema_retrieval/document_builder.py`
  - `engine/schema_retrieval/retriever.py`
  - `engine/schema_retrieval/vector_index.py`
  - `eval/run_eval.py`
  - `scripts/audit_m20_eval_ground_truth.py`
  - `scripts/smoke_m20_milvus_index.py`
  - `tests/test_m20_schema_index_hygiene.py`
  - `.agent_work/temp/m20-notes.md`
  - `.agent_work/temp/m20-eval-ground-truth-audit.md`
  - `.agent_work/temp/m20-milvus-index-smoke.md`
  - `.agent_work/temp/m20-*-diagnostic-*.json/.md/.jsonl` validation artifacts

## Implementation Checklist

- [x] Confirm decision boundary with user: do not change default model / embedding / vector backend, do not rewrite eval cases, do not switch `result_match` oracle to MySQL inside M20.
- [x] Freeze MySQL ground-truth audit into `.agent_work/temp/m20-eval-ground-truth-audit.md`.
- [x] Make Milvus collection lifecycle safe: clean unique experiment collections are allowed; polluted existing collections are refused unless reset.
- [x] Reuse one configured vector index inside an eval run so the same schema docs are not inserted once per case.
- [x] Add `schema_docs_hash` / collection metadata visibility to smoke/report artifacts.
- [x] Run focused tests, Milvus smoke, and at least one clean Milvus + Qwen embedding diagnostic run.
- [ ] Record validation snapshots and M20 conclusions in state docs during finish-docs.

## Confirmed Decisions

- Collection strategy: use unique experiment collection names for M20 eval/smoke, e.g. `datapilot_schema_docs_qwen_20260802_<run_id>`.
- Eval oracle strategy: keep current SQLite deterministic `result_match` oracle for M20, but make the oracle backend explicit in report/audit notes. Switching to MySQL is a future benchmark decision.
- Case strategy: do not change formal/challenge/diagnostic YAML cases in M20. Refund-rate wording, paid-order wording, and stronger formal result checks are documented as options only.

## Early Findings

- Existing `retrieve_schema()` built a configured vector index whenever `vector_index` was not explicitly passed.
- Because `/api/query` did not pass a shared index and `eval.run_eval` calls the API once per case, Milvus experiments could insert the same schema docs repeatedly into a fixed collection.

## Implementation Log

- Added `schema_documents_hash()` based on `doc_id + keyword_text + vector_text`.
- `MilvusVectorIndex` now records `initial_row_count / inserted_document_count / final_row_count`.
- Existing clean collection (`row_count == len(schema_docs)` and matching vector dimension) is reused without insert.
- Existing polluted collection raises `RuntimeError` and instructs the caller to use a unique `MILVUS_COLLECTION` or explicit `MILVUS_RESET_COLLECTION=true`.
- `eval.run_eval` now prebuilds one shared Milvus vector index for `--pipeline-mode new_text2sql` when `SCHEMA_VECTOR_BACKEND=milvus`, attaches it to `app.state`, and writes runtime metadata into Markdown reports.
- Current `result_match` oracle backend is explicitly reported as `sqlite_deterministic_seed`; M20 does not switch it to MySQL.

## Validation Snapshots

- Focused tests: `python -m pytest tests\test_m20_schema_index_hygiene.py tests\test_phase3a_schema_retrieval.py -q --basetemp=.agent_work\temp\pytest-m20-focused` -> `14 passed, 1 warning`.
- Compile check: `python -m py_compile ... scripts\smoke_m20_milvus_index.py` -> passed.
- MySQL audit: `python -m scripts.audit_m20_eval_ground_truth` -> `.agent_work/temp/m20-eval-ground-truth-audit.md`; 42 loaded cases, 14 `expected_sql`, MySQL execution `ok=14 error=0`.
- Default smoke eval: `python -m eval.run_eval --cases eval\cases\smoke.yaml --pipeline-mode new_text2sql ...` -> `passed=5/6`; report includes `result_match_oracle_backend=sqlite_deterministic_seed` and default `schema_vector_index_reuse=not_applicable`.
- Milvus index smoke: `python -m scripts.smoke_m20_milvus_index --output .agent_work\temp\m20-milvus-index-smoke.md` -> PASS; collection `datapilot_schema_docs_m20_20260802_203949_007d1e09`, `schema_docs_count=193`, `final_row_count=193`, `schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`.
- Clean Milvus + Qwen embedding diagnostic: DeepSeek `deepseek-v4-flash` + DashScope `qwen3.7-text-embedding`, unique collection `datapilot_schema_docs_m20_deepseek_qwenemb_20260802_a` -> `.agent_work/temp/m20-deepseek-qwenemb-diagnostic-report.md`, `passed=17/32`, `milvus_final_row_count=193`, `schema_vector_index_reuse=run_scoped`.
- Failure distribution compare: `.agent_work/temp/m20-m19-polluted-vs-clean-deepseek-qwenemb-compare.md`; clean run vs M19 polluted run changed failure mix (`unknown 2 -> 0`, `result_match 2 -> 1`, `schema_context 4 -> 5`, `query_plan 4 -> 5`) but did not show clear embedding benefit.
- Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic attempt timed out after 900s before report/triage finalization; partial trace has 21 lines and is not used as a conclusion.
- Related regression tests: `python -m pytest tests\test_phase3a_pipeline.py tests\test_m16_trace_router.py tests\test_m19_failure_triage.py tests\test_m20_schema_index_hygiene.py -q --basetemp=.agent_work\temp\pytest-m20-related` -> `27 passed, 1 warning`.
- Full pytest: first 300s run timed out mid-suite without failure output; rerun `python -m pytest -q --basetemp=.agent_work\temp\pytest-m20-full-2` -> `127 passed, 1 warning`.
- `git diff --check` -> only Windows LF/CRLF warnings for touched files; no whitespace errors.

## Finish-Module Comment Summary

- Coverage scan: checked changed code files and new scripts/tests. New public helpers/scripts/tests have module/function docstrings or explanatory comments; no missing class/function docstrings found in M20-owned code.
- Quality scan: comments now explain the new concepts `schema_documents_hash`, clean vs polluted Milvus collection, run-scoped vector index reuse, and SQLite oracle traceability.
- Internal readability scan: added/kept step comments around Milvus row-count guard, eval prebuild metadata, smoke collection check, and MySQL expected SQL audit.
- Format scan: comments are Chinese-first with focused ★ markers; no extra comment-only churn outside M20 files.

## References

- Internal project sources only: `docs/phase3b-langfuse-plan-v6.md` M20 section, `docs/state/AI_CONTEXT.md`, `docs/state/runbook.md`, `docs/state/eval-baselines.md`, `docs/state/database-current-state.md`, and current schema retrieval/eval code.
- No external web references were used.

## Leftovers / Next

- Qwen `qwen3.7-max` + clean Milvus + Qwen embedding full diagnostic timed out at 900s; rerun later with a longer timeout or a smaller first pass if this comparison is still needed.
- `result_match` still uses SQLite deterministic seed; switching to MySQL/current configured DB remains a separate benchmark口径 decision.
- Formal case strength and refund-rate / paid-order wording remain unchanged; any YAML changes need a separate user confirmation.
- Unique collection strategy avoids pollution but can grow Milvus collection count if experiments are kept; future tooling may add an explicit cleanup command for old `datapilot_schema_docs_m20_*` collections.

## Follow-up: Retrieval-only Embedding Benchmark

- Added `eval/cases/schema-retrieval-embedding-benchmark.yaml` with 10 cases covering synonym, semantic, relation, and hard-negative retrieval questions.
- Added `eval/run_schema_retrieval_benchmark.py`; it does not call LLM or execute SQL, and reports keyword-only / vector-only / merged recall separately.
- Added `tests/test_schema_retrieval_embedding_benchmark.py`.
- Deterministic baseline: `.agent_work/temp/schema-retrieval-embedding-deterministic-report.md` -> `avg_overall_recall=0.738`, `avg_keyword_overall_recall=0.738`, `avg_vector_overall_recall=0.787`.
- Milvus + DashScope Qwen embedding: `.agent_work/temp/schema-retrieval-embedding-qwen-milvus-report.md`, collection `datapilot_schema_retrieval_bench_qwen_20260802_223456_127f76ab`, `row_count=193` -> `avg_overall_recall=0.738`, `avg_keyword_overall_recall=0.738`, `avg_vector_overall_recall=0.929`.
- Conclusion: Qwen embedding shows clear vector-only recall improvement, but merged recall is unchanged; next retrieval work should evaluate fusion / RRF / rerank / top_k before changing default embedding.

## M20 Conclusion Draft

- M20 fixed the trust problem in the Milvus experiment path: clean collections now have traceable `row_count`, `schema_docs_hash`, embedding config, and run-scoped index reuse.
- Current clean DeepSeek + Qwen embedding diagnostic scored `17/32`, lower than the M19 polluted `19/32`; this does not prove Qwen embedding is worse, but it does prove the previous polluted index was not a valid basis for claiming a win.
- No defaults were changed: default retrieval remains `inmemory + deterministic`, and Milvus/Qwen embedding remain explicit experiment settings.
- No eval case semantics were changed: MySQL audit records the ground truth state, while `result_match` remains SQLite deterministic oracle until a separate benchmark decision.
