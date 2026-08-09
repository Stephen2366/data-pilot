# DataPilot M27 Eval Report

- run_id: `m27-core-20260809-qwen37max-local-04`
- run_status: `completed`
- contract_version: `m27-v1`
- artifact_schema_version: `m27-artifact-v1`
- projector_version: `m27-projector-v1`
- catalog_hash: `61792660460e4eae8b644e9c20307c8955f3d2f99966b7064750a8d068cbf1e8`
- selected_contract_hash: `15db22c5c3571317929b092acba7040baad80244e165a91c2041bd47ff7d683a`
- suite_policy_hash: `b7212e6504d5cb09e7641cf9115050d15622fe16269de07d20476da94257312e`
- run_spec_hash: `b9243513fcd92978100111b04dd525ea7147f0eb97e68c9bddec83de8c897708`

## Gate

- suite: `core`
- outcome: **failed**
- required: passed=13, failed=20, not_observed=1

## Execution

- logical_completed: 19
- logical_external_unavailable: 0
- logical_pipeline_error: 0
- logical_scenarios: 19
- physical_attempts: 19

## Assertion views

| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| expected_rejection | 3 | 3 | 3 | 0 | 0 | 0 | 0 |
| metric_mapping | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| output_contract | 10 | 10 | 1 | 9 | 0 | 0 | 0 |
| query_plan | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| result_match | 10 | 10 | 1 | 9 | 0 | 0 | 0 |
| safety_block | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| schema_context | 4 | 4 | 2 | 2 | 0 | 0 | 0 |
| trace_complete | 1 | 1 | 1 | 0 | 0 | 0 | 0 |

自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。
