# M19 A/B Failure Distribution

- left: .agent_work\temp\m19-qwen37max-qwenemb-diagnostic-triage.json
- right: .agent_work\temp\m20-qwen37max-qwenemb-diagnostic-triage.json

| failure_stage | left | right | delta_right_minus_left |
|---|---:|---:|---:|
| plan_validation | 1 | 0 | -1 |
| query_plan | 1 | 0 | -1 |
| result_match | 1 | 1 | 0 |
| schema_context | 7 | 7 | 0 |
| schema_retrieval | 1 | 1 | 0 |
| sql_generation | 1 | 2 | 1 |
| unknown | 1 | 2 | 1 |