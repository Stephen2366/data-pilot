# M19 A/B Failure Distribution

- left: .agent_work\temp\m19-qwen37max-diagnostic-triage.json
- right: .agent_work\temp\m19-qwen37max-qwenemb-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 1 | 1 | 0 |
| query_plan | 0 | 1 | 1 |
| result_match | 1 | 1 | 0 |
| schema_context | 6 | 7 | 1 |
| schema_retrieval | 2 | 1 | -1 |
| sql_generation | 0 | 1 | 1 |
| unknown | 1 | 1 | 0 |