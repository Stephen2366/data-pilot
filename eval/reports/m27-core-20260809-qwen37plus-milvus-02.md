# DataPilot M27 Eval Report

- run_id: `m27-core-20260809-qwen37plus-milvus-02`
- run_status: `completed`
- contract_version: `m27-v2`
- artifact_schema_version: `m27-artifact-v1`
- projector_version: `m27-projector-v1`
- catalog_hash: `bcec61940283bf3a3027c2a93b90a972322fba2642eda361b77ecb19c4757dcf`
- selected_contract_hash: `2f452137426f059096be1baa5713debdcfd2601e25d107987c91b55b02639b74`
- suite_policy_hash: `b7212e6504d5cb09e7641cf9115050d15622fe16269de07d20476da94257312e`
- run_spec_hash: `74b268e01a2369bacf31892797c39141bde432c3f898f48c60dbd099f53ad68d`

## Gate

- suite: `core`
- outcome: **inconclusive**
- required: passed=28, failed=0, not_observed=6

## Execution

- logical_completed: 17
- logical_external_unavailable: 2
- logical_pipeline_error: 0
- logical_scenarios: 19
- physical_attempts: 19

## Assertion views

| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| expected_rejection | 3 | 3 | 3 | 0 | 0 | 0 | 0 |
| metric_mapping | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| output_contract | 10 | 8 | 8 | 0 | 2 | 2 | 0 |
| query_plan | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| result_match | 10 | 8 | 8 | 0 | 2 | 2 | 0 |
| safety_block | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| schema_context | 4 | 2 | 2 | 0 | 2 | 2 | 0 |
| trace_complete | 1 | 1 | 1 | 0 | 0 | 0 | 0 |

自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。
