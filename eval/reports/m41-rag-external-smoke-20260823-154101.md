# Phase 4 RAG E2E Eval Report

- run_id: `m41-rag-external-smoke-20260823-154101`
- artifact_identity: `9e31fab3faf836b8509e227000261da89023df074d8aa50322f71b95a4a3b7f4`
- Gate: **failed**
- required: passed=96 / failed=12 / not_observed=0

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0016 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0047 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0019 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0386 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0461 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0181 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0420 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0431 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0318 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 108 | 96 | 12 | 0 |
| advisory | 27 | 18 | 9 | 0 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:multi_document | 2 | citation=1, selection=1 | 20/4/0 | 2/1/1/0 |
| cardinality:single_document | 7 | citation=1, passed=4, retrieval=1, selection=1 | 76/8/0 | 6/5/5/4 |
| difficulty:basic | 3 | passed=1, retrieval=1, selection=1 | 29/7/0 | 2/1/1/1 |
| difficulty:core | 3 | citation=1, passed=2 | 35/1/0 | 3/3/3/2 |
| difficulty:hard | 3 | citation=1, passed=1, selection=1 | 32/4/0 | 3/2/2/1 |
| partition:external_dev | 9 | citation=2, passed=4, retrieval=1, selection=2 | 96/12/0 | 8/6/6/4 |
| source:confluence | 3 | passed=1, retrieval=1, selection=1 | 29/7/0 | 2/1/1/1 |
| source:confluence+google_drive | 1 | citation=1 | 11/1/0 | 1/1/1/0 |
| source:google_drive | 2 | passed=1, selection=1 | 21/3/0 | 2/1/1/1 |
| source:jira | 3 | citation=1, passed=2 | 35/1/0 | 3/3/3/2 |
| type:basic | 3 | passed=1, retrieval=1, selection=1 | 29/7/0 | 2/1/1/1 |
| type:completeness | 1 | selection=1 | 9/3/0 | 1/0/0/0 |
| type:conflicting_info | 1 | citation=1 | 11/1/0 | 1/1/1/0 |
| type:constrained | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:intra_document_reasoning | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:miscellaneous | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:semantic | 1 | citation=1 | 11/1/0 | 1/1/1/0 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
