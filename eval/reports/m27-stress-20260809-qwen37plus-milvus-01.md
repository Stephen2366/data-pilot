# DataPilot M27 Eval Report

- run_id: `m27-stress-20260809-qwen37plus-milvus-01`
- run_status: `completed`
- contract_version: `m27-v2`
- artifact_schema_version: `m27-artifact-v1`
- projector_version: `m27-projector-v1`
- catalog_hash: `bcec61940283bf3a3027c2a93b90a972322fba2642eda361b77ecb19c4757dcf`
- selected_contract_hash: `c2dadfca6c435dda665f4756cc85d317ccc7e87c3c892e008108621bc528bb37`
- suite_policy_hash: `c59642a95e934d54517b64cee956854accc72dc049605761c68aecbb886b1d46`
- run_spec_hash: `a9ef3cf0befc3e5531148f26fb9b2990bbc88e9a8b735a0150ace85902019c81`

## Gate

- suite: `stress`
- outcome: **inconclusive**
- required: passed=0, failed=0, not_observed=0

## Execution

- logical_completed: 7
- logical_external_unavailable: 2
- logical_pipeline_error: 0
- logical_scenarios: 9
- physical_attempts: 9

## Assertion views

| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| join_path | 2 | 2 | 0 | 2 | 0 | 0 | 0 |
| output_contract | 9 | 7 | 5 | 2 | 2 | 2 | 0 |
| query_plan | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| result_match | 9 | 7 | 2 | 5 | 2 | 2 | 0 |
| schema_context | 4 | 4 | 0 | 4 | 0 | 0 | 0 |

自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。
