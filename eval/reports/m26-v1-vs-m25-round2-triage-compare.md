# M19 A/B Failure Distribution

- left: .agent_work\temp\m25-round2-qwen37plus-local-triage.json
- right: eval\reports\m26-v1-qwen37plus-local-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| output_contract | 1 | 0 | -1 |
| query_plan | 3 | 4 | 1 |
| result_match | 0 | 1 | 1 |
| schema_context | 0 | 1 | 1 |
| unknown | 1 | 1 | 0 |

## Failure Subtype Distribution

| failure_subtype | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| output_column_contract | 1 | 0 | -1 |
| result_contract | 0 | 1 | 1 |
| scorer_contract | 0 | 1 | 1 |