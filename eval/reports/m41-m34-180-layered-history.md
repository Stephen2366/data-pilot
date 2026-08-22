# M34 180题分层历史诊断

- questions: `180`
- source artifact: `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`
- product API/Router/Harness: `not_observed`（旧运行直接调用 AnswerFlow）
- selected / generation-visible logical IDs: `not_observed`（旧 artifact 未保存）

| stratum | questions | primary diagnosis |
|---|---:|---|
| cardinality:multi_document | 38 | answer_exact_fact_lower_bound=2, citation=18, composer_support=3, retrieval=15 |
| cardinality:single_document | 142 | answer_exact_fact_lower_bound=77, citation=26, composer_support=12, passed=1, retrieval=26 |
| overall | 180 | answer_exact_fact_lower_bound=79, citation=44, composer_support=15, passed=1, retrieval=41 |
| partition:diagnostic_dev | 60 | answer_exact_fact_lower_bound=24, citation=18, composer_support=4, retrieval=14 |
| partition:held_out | 120 | answer_exact_fact_lower_bound=55, citation=26, composer_support=11, passed=1, retrieval=27 |
| source:confluence | 64 | answer_exact_fact_lower_bound=24, citation=14, composer_support=4, retrieval=22 |
| source:confluence+google_drive | 6 | answer_exact_fact_lower_bound=1, citation=5 |
| source:confluence+jira | 6 | citation=3, composer_support=2, retrieval=1 |
| source:google_drive | 42 | answer_exact_fact_lower_bound=18, citation=10, composer_support=4, retrieval=10 |
| source:google_drive+jira | 2 | citation=2 |
| source:jira | 60 | answer_exact_fact_lower_bound=36, citation=10, composer_support=5, passed=1, retrieval=8 |
| type:basic | 64 | answer_exact_fact_lower_bound=40, citation=11, composer_support=6, passed=1, retrieval=6 |
| type:completeness | 13 | citation=4, retrieval=9 |
| type:conflicting_info | 8 | answer_exact_fact_lower_bound=1, citation=7 |
| type:constrained | 25 | answer_exact_fact_lower_bound=11, citation=5, composer_support=4, retrieval=5 |
| type:intra_document_reasoning | 4 | answer_exact_fact_lower_bound=4 |
| type:miscellaneous | 8 | answer_exact_fact_lower_bound=8 |
| type:project_related | 6 | citation=3, composer_support=2, retrieval=1 |
| type:semantic | 52 | answer_exact_fact_lower_bound=15, citation=14, composer_support=3, retrieval=20 |

## 边界

- `answer_exact_fact_lower_bound` 是保守字符串下限，不能冒充语义错误率。
- 本报告零 Tool/LLM 调用，只消费冻结的 M34 Answer/Retrieval artifacts。
- 逐题 funnel 见同次生成的 JSON；M41 external 产品运行另行分账。
