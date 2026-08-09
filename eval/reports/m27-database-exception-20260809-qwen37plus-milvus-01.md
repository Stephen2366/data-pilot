# DataPilot M27 Eval Report

- run_id: `m27-database-exception-20260809-qwen37plus-milvus-01`
- run_status: `completed`
- contract_version: `m27-v2`
- artifact_schema_version: `m27-artifact-v1`
- projector_version: `m27-projector-v1`
- catalog_hash: `bcec61940283bf3a3027c2a93b90a972322fba2642eda361b77ecb19c4757dcf`
- selected_contract_hash: `ee002dc5ef7d64ca52e0fed7d88ad94110e3861988a07f11c74aa8d2ec25e407`
- suite_policy_hash: `1bea7794c648ab2ad3f6870e3e2af8a1a8399978b54759a45c0fbcb45defc7f0`
- run_spec_hash: `72a01a99353c7ad4e04690d68f8472365931dd68454dc3d22f75ebbc4e6ae7f3`

## Gate

- suite: `database_exception`
- outcome: **inconclusive**
- required: passed=0, failed=0, not_observed=0

## Execution

- logical_completed: 3
- logical_external_unavailable: 4
- logical_pipeline_error: 0
- logical_scenarios: 7
- physical_attempts: 7

## Assertion views

| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| join_path | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| output_contract | 7 | 3 | 2 | 1 | 4 | 4 | 0 |
| result_match | 7 | 3 | 2 | 1 | 4 | 4 | 0 |
| schema_context | 4 | 2 | 0 | 2 | 2 | 2 | 0 |

自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。
