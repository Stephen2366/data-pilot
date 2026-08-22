# DataPilot M27 Eval Report

- run_id: `m41-real-llm-smoke-20260822-01`
- run_status: `completed`
- contract_version: `m27-v3`
- artifact_schema_version: `m27-artifact-v1`
- projector_version: `m27-projector-v1`
- catalog_hash: `ced2194d3bcfe42c4551efe23b5a3979c3b79dd03e568e357dfe1e6a8df55d92`
- selected_contract_hash: `c283f1afbbe4b9a2a58a810b5fdbc430be40256407dbe0144b70f3ee44a4df19`
- suite_policy_hash: `5b0cb99af5449edf6f67e003bf7132d928ed53a02c76e82e6d4b6598e2674dbb`
- run_spec_hash: `bd3ce4aefd4ccebfad5ecd364548aeec87deb49ee931d80000c2b6139e98d07f`

## Gate

- suite: `smoke`
- outcome: **inconclusive**
- required: passed=2, failed=0, not_observed=7

## Execution

- logical_completed: 2
- logical_external_unavailable: 2
- logical_pipeline_error: 0
- logical_scenarios: 4
- physical_attempts: 4

## Assertion views

| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| expected_rejection | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| output_contract | 2 | 0 | 0 | 0 | 2 | 2 | 0 |
| query_plan | 1 | 0 | 0 | 0 | 1 | 1 | 0 |
| result_match | 2 | 0 | 0 | 0 | 2 | 2 | 0 |
| safety_block | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| schema_context | 1 | 0 | 0 | 0 | 1 | 1 | 0 |
| trace_complete | 1 | 0 | 0 | 0 | 1 | 1 | 0 |

自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。
