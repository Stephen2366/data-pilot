# M19 A/B Failure Distribution

- left: .agent_work\temp\m21-qwen-plus-weighted-diagnostic-triage.json
- right: .agent_work\temp\m21-qwen-plus-rrf-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| query_plan | 1 | 2 | 1 |
| result_match | 1 | 2 | 1 |
| schema_context | 6 | 5 | -1 |
| schema_retrieval | 2 | 2 | 0 |
| sql_generation | 1 | 1 | 0 |
| unknown | 2 | 1 | -1 |