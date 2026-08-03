# M19 A/B Failure Distribution

- left: .agent_work\temp\m19-diagnostic-triage.json
- right: .agent_work\temp\m19-qwen37max-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 1 | 1 | 0 |
| query_plan | 1 | 0 | -1 |
| result_match | 2 | 1 | -1 |
| schema_context | 6 | 6 | 0 |
| schema_retrieval | 1 | 2 | 1 |
| sql_generation | 1 | 0 | -1 |
| sql_guard | 1 | 0 | -1 |
| unknown | 2 | 1 | -1 |