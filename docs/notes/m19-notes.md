# M19 notes

## Module scope / changed files
- Module: M19 Trace Failure Triage / LangFuse-driven Eval Analysis.
- M19-owned code/test files: `eval/triage.py`, `eval/run_eval.py`, `tests/test_m19_failure_triage.py`.
- M19 documentation/material files: `docs/AI_CONTEXT.md`, `docs/AI_CONTEXT_CHANGELOG.md`, `docs/dev-log.md`, `.agent_work/temp/m19-notes.md`.
- Existing dirty files not owned by this module were preserved and not reverted: `.claude/skills/accept-module/SKILL.md`, `docs/database-current-state.md`, and pre-existing edits inside `docs/dev-log.md` / `docs/AI_CONTEXT_CHANGELOG.md`.

## Implementation checklist
- [x] Add local failure triage taxonomy and heuristics.
- [x] Add Failure Triage Summary to eval Markdown reports.
- [x] Add optional triage JSON output for local A/B failure distribution comparison.
- [x] Reuse LangFuse score writer for triage score payloads, with skipped/failed degradation.
- [x] Add focused tests for SQL guard / SQL execution / result_match or scorer_issue triage.
- [x] Run M19 verification commands, then finish-module and finish-docs.

## Decisions / boundaries
- M19 stays local-first. LangFuse is only a score/metadata enhancement when JSONL has `langfuse_write_status=ok`.
- M19 will not auto-create Dataset, mutate eval case YAML, add a database table, or implement a webhook runner.
- First-pass triage is heuristic and evidence-based, not a definitive root-cause oracle; ambiguous cases must keep `unknown` / `manual_review`.
- Pitfall found during smoke: expected security blocks can have `passed=True` and `error_type=sql_guard_blocked`; triage failure status must follow eval pass/skipped/review/status, not raw `error_type` alone.

## Implementation notes
- Added `eval/triage.py` as the M19 single fact source for `FailureTriage`, stage/action taxonomy, JSONL trace loading, heuristic classification, triage JSON, LangFuse triage score payloads, and local failure distribution comparison.
- `eval/run_eval.py` now appends `Failure Triage Summary` to Markdown reports, supports `--triage-json`, and supports local compare mode via `--compare-triage-left/--compare-triage-right/--compare-triage-report`.
- LangFuse triage writes use four scores per case: `triage:failed`, `triage:failure_stage`, `triage:needs_action`, `triage:confidence`. Missing/failed LangFuse trace mappings are counted as skipped and do not affect local reports.
- Regression candidates are suggestions only. M19 does not write back to `eval/cases/*`.

## Verification snapshot
- Focused tests: `python -m pytest tests\test_m19_failure_triage.py tests\test_m17_scorers.py --basetemp=.agent_work\temp\pytest-m19-b` -> 15 passed.
- M16-M19 focused tests: `python -m pytest tests\test_m19_failure_triage.py tests\test_m18_phase3b_smoke.py tests\test_m17_scorers.py tests\test_m16_trace_router.py --basetemp=.agent_work\temp\pytest-m19-c` -> 31 passed.
- Default local smoke: `python -m eval.run_eval --cases eval\cases\smoke.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\m19-smoke-traces.jsonl --report .agent_work\temp\m19-smoke-report.md --triage-json .agent_work\temp\m19-smoke-triage.json` -> passed=6/6, `langfuse_triage_scores=ok:0 skipped:24 failed:0`.
- LangFuse enabled smoke with proxy: `LANGFUSE_ENABLED=true` + `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`, same smoke command with `m19-langfuse-smoke-*` outputs -> passed=5/6, `langfuse_scores=ok:27`, `langfuse_triage_scores=ok:24`.
- Formal eval: `.agent_work\temp\m19-formal-report.md` / `.agent_work\temp\m19-formal-triage.json` -> passed=7/10; triage stages `schema_context=1`, `plan_validation=1`, `query_plan=1`.
- Challenge eval: `.agent_work\temp\m19-challenge-report.md` / `.agent_work\temp\m19-challenge-triage.json` -> passed=9/16; triage stages `schema_context=1`, `result_match=3`, `query_plan=3`, `unknown=1`.
- Diagnostic eval: `.agent_work\temp\m19-diagnostic-report.md` / `.agent_work\temp\m19-diagnostic-triage.json` -> passed=19/32; triage stages `schema_context=6`, `schema_retrieval=1`, `result_match=2`, `plan_validation=1`, `sql_guard=1`, `unknown=2`, `query_plan=1`, `sql_generation=1`; actions `fix_schema_desc=7`, `fix_pipeline=5`, `manual_review=3`.
- Local A/B distribution compare: `.agent_work\temp\m19-formal-vs-challenge-triage-compare.md`.
- Full pytest: `python -m pytest --basetemp=.agent_work\temp\pytest-m19-full` -> 121 passed, 2 skipped, 1 warning.
- Post-comment quick check: `python -m pytest tests\test_m19_failure_triage.py --basetemp=.agent_work\temp\pytest-m19-comment` -> 5 passed, 1 warning.

## finish-module comment review
- Coverage scan: M19-owned `eval/triage.py` has module docstring, `FailureTriage` class docstring, and docstrings for all public/private helper functions. `tests/test_m19_failure_triage.py` has module docstring and helper/test docstrings. `eval/run_eval.py` added `_append_failure_triage_summary()` with docstring; existing touched `main()` / `write_report()` already had docstrings.
- Quality scan: New concepts explained in comments/docstrings: failure triage, local-first report, LangFuse optional score payload, A/B failure distribution, regression candidate boundary. Key decision explained: trace/scorer evidence stays local-first; LangFuse only filters/scores when mapping is confirmed.
- Readability scan: Added step comments inside `triage_result()` for passed-case triage, trace-step evidence, error_type fallback, and scorer-detail fallback.
- Format scan: Comments are Chinese-first and use ★ only for key module/design points. No missing comments found after the final scan.

## References
- No external reference was needed for M19 implementation. The module followed `docs/phase3b-langfuse-plan-v6.md` M19 taxonomy and existing M16-M18 DataPilot trace/scorer/LangFuse score APIs.

## Known limits
- Heuristic triage currently maps missing columns to `schema_context`; some of these may later prove to be SQL alias / scorer strictness issues. Keep `failure_reason` and `evidence_step` visible in reports.
- Diagnostic failures with `review_required=True` keep `manual_review` even if a trace step points to a concrete stage, so difficult/ambiguous cases do not get over-claimed as automatic fix candidates.

## Follow-up analysis on 2026-08-02
- Containment caveat: formal / challenge / diagnostic reports were produced by separate LLM eval runs, not by slicing one superset run. Duplicate `case_id` results differed between challenge and diagnostic for 6 cases: `db_core_001`, `db_core_002`, `db_core_004`, `db_hard_001`, `db_multi_002`, `db_multi_004`.
- Interpretation: repeated-case differences are expected under real LLM nondeterminism and should not be over-read as benchmark definition contradictions. For strict containment comparison, run the superset once and slice subsets from the same result file.
- Qwen availability probe: `LLM_PROVIDER=qwen; QWEN_MODEL=qwen3.8-max` returned DashScope HTTP 403 `access_denied`, so current account/config cannot use this model. Control probe with `QWEN_MODEL=qwen3.7-max` returned `{"ok": true}`, so DashScope key/base URL are working.

## qwen3.7-max follow-up eval on 2026-08-02
- User requested running the three M19 eval sets with `qwen3.7-max` after `qwen3.8-max` was unavailable.
- Config used for all three commands: `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.7-max`, `LANGFUSE_ENABLED=false`. This was an explicit run only; default `.env` / fallback model was not changed.
- Formal: `.agent_work\temp\m19-qwen37max-formal-report.md` / `.agent_work\temp\m19-qwen37max-formal-triage.json` -> passed=8/10; triage `schema_context=2`, actions `fix_schema_desc=2`; failures were `p3a_multi_001` missing `coupon_order_count` and `p3a_multi_003` missing `category`.
- Challenge: `.agent_work\temp\m19-qwen37max-challenge-report.md` / `.agent_work\temp\m19-qwen37max-challenge-triage.json` -> command line passed=12/16; triage summary failed=5 because it includes one `review_required` manual case; stages `result_match=1`, `schema_context=1`, `query_plan=1`, `schema_retrieval=1`, `unknown=1`.
- Diagnostic: `.agent_work\temp\m19-qwen37max-diagnostic-report.md` / `.agent_work\temp\m19-qwen37max-diagnostic-triage.json` -> command line passed=22/32; triage summary failed=11 because it includes one `review_required` manual case; stages `schema_context=6`, `schema_retrieval=2`, `result_match=1`, `plan_validation=1`, `unknown=1`; actions `fix_schema_desc=6`, `fix_pipeline=2`, `manual_review=3`.
- DeepSeek flash vs qwen3.7-max diagnostic compare: `.agent_work\temp\m19-deepseek-vs-qwen37max-diagnostic-triage-compare.md`. Qwen scored higher in this M19 snapshot and reduced generation/security/result mismatch failures, but `schema_context` stayed at 6 and `schema_retrieval` increased from 1 to 2.
- Recommendation recorded: keep qwen3.7-max as an explicit candidate / A/B model. Do not switch default inside M19 without a separate baseline decision because model choice affects long-term eval baselines.
