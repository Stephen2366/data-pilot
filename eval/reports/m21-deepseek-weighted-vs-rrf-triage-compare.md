# M19 A/B Failure Distribution

- left: .agent_work\temp\m21-deepseek-weighted-diagnostic-triage.json
- right: .agent_work\temp\m21-deepseek-rrf-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 0 | 3 | 3 |
| query_plan | 3 | 4 | 1 |
| result_match | 1 | 1 | 0 |
| schema_context | 5 | 4 | -1 |
| schema_retrieval | 0 | 1 | 1 |
| sql_generation | 1 | 0 | -1 |
| sql_guard | 1 | 1 | 0 |
| unknown | 2 | 1 | -1 |