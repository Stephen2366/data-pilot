# M19 A/B Failure Distribution

- left: .agent_work\temp\m19-deepseek-qwenemb-diagnostic-triage.json
- right: .agent_work\temp\m20-deepseek-qwenemb-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 1 | 2 | 1 |
| query_plan | 4 | 5 | 1 |
| result_match | 2 | 1 | -1 |
| schema_context | 4 | 5 | 1 |
| schema_retrieval | 1 | 1 | 0 |
| sql_guard | 1 | 1 | 0 |
| unknown | 2 | 0 | -2 |