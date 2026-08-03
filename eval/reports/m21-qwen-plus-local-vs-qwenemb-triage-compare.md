# M19 A/B Failure Distribution

- left: .agent_work\temp\m21-qwen-plus-local-weighted-triage.json
- right: .agent_work\temp\m21-qwen-plus-qwenemb-weighted-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| query_plan | 0 | 1 | 1 |
| result_match | 1 | 1 | 0 |
| schema_context | 6 | 6 | 0 |
| schema_retrieval | 2 | 2 | 0 |
| sql_generation | 2 | 1 | -1 |
| unknown | 2 | 1 | -1 |

## Failure Subtype Distribution

| failure_subtype | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| output_column_contract | 6 | 6 | 0 |
| output_table_contract | 2 | 2 | 0 |
| result_contract | 1 | 1 | 0 |