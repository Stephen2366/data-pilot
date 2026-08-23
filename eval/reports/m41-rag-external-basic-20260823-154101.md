# Phase 4 RAG E2E Eval Report

- run_id: `m41-rag-external-basic-20260823-154101`
- artifact_identity: `10836eef6c459606dde95a3c299f7233d389ded68fb8df2f29ef6a1f96799c28`
- Gate: **failed**
- required: passed=215 / failed=25 / not_observed=12

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0016 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0019 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0022 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0023 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0029 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0031 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0045 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0047 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0050 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0059 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0062 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0079 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0086 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0091 | 1 | rag/failed/no_answer/passed | 5 | 3 | 3 | 0 | product_runtime |
| qst_0116 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0117 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0118 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0122 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0151 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0155 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0157 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 252 | 215 | 25 | 12 |
| advisory | 63 | 36 | 24 | 3 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:single_document | 21 | citation=1, passed=12, product_runtime=3, retrieval=4, selection=1 | 215/25/12 | 15/14/14/12 |
| difficulty:basic | 21 | citation=1, passed=12, product_runtime=3, retrieval=4, selection=1 | 215/25/12 | 15/14/14/12 |
| partition:external_dev | 21 | citation=1, passed=12, product_runtime=3, retrieval=4, selection=1 | 215/25/12 | 15/14/14/12 |
| source:confluence | 6 | citation=1, passed=2, product_runtime=1, retrieval=2 | 56/11/5 | 3/3/3/2 |
| source:google_drive | 8 | passed=4, product_runtime=1, retrieval=2, selection=1 | 82/12/2 | 6/5/5/4 |
| source:jira | 7 | passed=6, product_runtime=1 | 77/2/5 | 6/6/6/6 |
| type:basic | 21 | citation=1, passed=12, product_runtime=3, retrieval=4, selection=1 | 215/25/12 | 15/14/14/12 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
