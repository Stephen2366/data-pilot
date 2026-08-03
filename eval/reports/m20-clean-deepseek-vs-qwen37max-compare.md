# M19 A/B Failure Distribution

- left: .agent_work\temp\m20-deepseek-qwenemb-diagnostic-triage.json
- right: .agent_work\temp\m20-qwen37max-qwenemb-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 2 | 0 | -2 |
| query_plan | 5 | 0 | -5 |
| result_match | 1 | 1 | 0 |
| schema_context | 5 | 7 | 2 |
| schema_retrieval | 1 | 1 | 0 |
| sql_generation | 0 | 2 | 2 |
| sql_guard | 1 | 0 | -1 |
| unknown | 0 | 2 | 2 |