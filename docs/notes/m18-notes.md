# M18 notes

## Implementation checklist
- [x] Add `scripts/smoke_phase3b_langfuse.py` for JSONL/API/LangFuse trace+score smoke.
- [x] Add focused tests for disabled / require-langfuse / trace mapping behavior where practical.
- [x] Run local disabled smoke and real LangFuse required smoke.
- [x] Record manual Experiment status honestly; do not replace UI workflow with unconfirmed automation.
- [x] Call finish-module after verification.

## Decisions / boundaries
- M18 stays a phase-close smoke and documentation module. It does not change `/api/query`, scorer semantics, or LangFuse evaluator architecture.
- LangFuse Scores can be written by `trace_id` before trace visibility is confirmed, per official docs; smoke reports score write and trace visibility as separate checks.
- The plan's Experiment workflow is manual. Unless user confirms switching to API/SDK experiment creation, do not claim UI Experiment completion from code alone.

## Smoke results
- Disabled/default smoke: PASS for config snapshot, `/api/query`, JSONL trace match; LangFuse mapping/score/visibility SKIP because `LANGFUSE_ENABLED=false`.
- Required LangFuse smoke without proxy: trace mapping PASS and score write PASS, but trace visibility query failed with Windows `WinError 10013` socket permission error.
- Required LangFuse smoke with `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`: all checks PASS; trace `b920c0b518504ce8a12a0c591bd1193c`, JSONL `langfuse_write_status=ok`, score `rule:m18_smoke` ok=1, observations=5 visible immediately.

## Active caveat
- On this Windows environment, LangFuse Cloud query/OTLP export may need Clash proxy env vars. Score write can still return ok without trace visibility, so M18 smoke keeps score write and visibility query as separate checks.

## Experiment workflow smoke materials
Selected 5 temporary cases in `.agent_work/temp/m18-experiment-workflow-cases.yaml`:
- table_hit/simple: `m18_table_hit_p3a_simple_001`
- expected_value: `m18_expected_value_p3a_agg_001`
- result_match: `m18_result_match_db_core_004` (borrowed from challenge-style result_match because formal regression uses expected_value/contains)
- safety/blocking: `m18_safety_p3a_sec_001`
- complex multi-table: `m18_complex_p3a_multi_001`

DeepSeek run command used env override, not `.env` edits. Result: passed=4/5, `langfuse_scores=ok:25 skipped:0 failed:0`, report `.agent_work/temp/m18-experiment-deepseek-report.md`, trace `.agent_work/temp/m18-experiment-deepseek-traces.jsonl`.
Qwen qwen3.7-plus run command used env override, not `.env` edits. Result: passed=3/5, `langfuse_scores=ok:22 skipped:0 failed:0`, report `.agent_work/temp/m18-experiment-qwen37-plus-report.md`, trace `.agent_work/temp/m18-experiment-qwen37-plus-traces.jsonl`.

Trace URLs for manual LangFuse UI workflow:
- DeepSeek table/simple: https://jp.cloud.langfuse.com/project/traces/128e1aec5c174c91b2324fe87b06f417
- DeepSeek expected_value: https://jp.cloud.langfuse.com/project/traces/723c3f024b714d0eba1b3357d8e458bb
- DeepSeek result_match: https://jp.cloud.langfuse.com/project/traces/13afda86ad824747bade537a2e0ebf6e
- DeepSeek safety: https://jp.cloud.langfuse.com/project/traces/<REDACTED_LANGFUSE_TRACE_ID>
- DeepSeek complex: https://jp.cloud.langfuse.com/project/traces/<REDACTED_LANGFUSE_TRACE_ID>
- Qwen table/simple: https://jp.cloud.langfuse.com/project/traces/b4706b8494694ea8858f35bf51505e68
- Qwen expected_value: https://jp.cloud.langfuse.com/project/traces/a598e327d911436d8c5b3d7e929dd24b
- Qwen result_match: https://jp.cloud.langfuse.com/project/traces/39e4315fb91c4047895740390156e95d
- Qwen safety: https://jp.cloud.langfuse.com/project/traces/fc29b23f5e19495da46fd06f13ac0375
- Qwen complex: https://jp.cloud.langfuse.com/project/traces/fa74bbf02123413f93c8e89a0fc9b4bd

Manual UI status: pending user operation. Need record UX evaluation, whether it satisfies EvalBench needs, and any blocking issue after user completes UI steps.

## Manual UI dataset export review
- User created Dataset `datapilot-m18-workflow-smoke-20260730` in LangFuse UI and exported `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv`.
- Export fields: `id`, `projectId`, `datasetId`, `sourceTraceId`, `sourceObservationId`, `status`, `createdAt`, `updatedAt`, `validFrom`, `input`, `expectedOutput`, `metadata`, `datasetName`, `htmlSourcePath`.
- Row count: 5, all `status=ACTIVE`, all linked to DeepSeek LangFuse trace ids.
- Dataset creation conclusion: trace -> dataset item workflow is usable.
- Caveat: one item (`sourceTraceId=128e1aec5c174c91b2324fe87b06f417`) appears to use a step/span style input (`{"summary":"查询 active 商品列表前 10 条"}`) and expected output (`{"status":"success","summary":"merged_hits=30"}`) instead of the root query/answer shape. For M18 workflow smoke this is acceptable, but future EvalBench dataset creation should normalize item input/expected output from case definitions or root trace, not arbitrary observations/spans.
- Export metadata includes telemetry noise and LangFuse public key (`scope.attributes.public_key`). This is not the secret key, but future reusable datasets should clean metadata to avoid clutter and accidental exposure of implementation details.
- UI run conclusion from user report: `Run experiment -> via User Interface` requires project LLM API key and prompt/model configuration; `via Webhook` requires a remote experiment URL. Current DataPilot has no webhook runner, so M18 should record Experiment UI as partially satisfying needs: dataset management works, pure manual existing-trace run comparison is not supported by this UI path.
