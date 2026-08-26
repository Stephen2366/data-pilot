# Phase 4 RAG E2E Eval Report

- run_id: `m46-historical-paired-20260826-160237-pipeline`
- artifact_identity: `b01fa4e34384ae7b93cc0dc62ae354cf5193671576674857e97de08aa3dbbfc4`
- Gate: **failed**
- required: passed=571 / failed=112 / not_observed=37

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0016 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0019 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0022 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | selection |
| qst_0023 | 1 | rag/failed/no_answer/passed | 5 | 3 | 3 | 0 | product_runtime |
| qst_0029 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0031 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0045 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0047 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0050 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0059 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0062 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0079 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0086 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0091 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0116 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0117 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0118 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0122 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0151 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0155 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0157 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0181 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0186 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0198 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0199 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 3 | retrieval |
| qst_0200 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0211 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0215 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0216 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0233 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0236 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0248 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0252 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0268 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0272 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0279 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0282 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0283 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0289 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0318 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0338 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0341 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0353 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0384 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0386 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0387 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0388 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0389 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0393 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0400 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0408 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0420 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0428 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0431 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0433 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0442 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0447 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0457 | 1 | rag/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0461 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0462 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 720 | 571 | 112 | 37 |
| advisory | 180 | 104 | 68 | 8 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:multi_document | 12 | citation=1, passed=1, product_runtime=4, retrieval=6 | 91/33/20 | 2/2/2/1 |
| cardinality:single_document | 48 | citation=2, passed=24, product_runtime=4, retrieval=16, selection=2 | 480/79/17 | 29/27/27/24 |
| difficulty:basic | 21 | citation=1, passed=14, product_runtime=1, retrieval=4, selection=1 | 229/21/2 | 17/16/16/14 |
| difficulty:core | 25 | passed=9, product_runtime=3, retrieval=12, selection=1 | 228/57/15 | 10/9/9/9 |
| difficulty:hard | 14 | citation=2, passed=2, product_runtime=4, retrieval=6 | 114/34/20 | 4/4/4/2 |
| partition:external_dev | 60 | citation=3, passed=25, product_runtime=8, retrieval=22, selection=2 | 571/112/37 | 31/29/29/25 |
| source:confluence | 22 | citation=1, passed=5, product_runtime=6, retrieval=8, selection=2 | 187/50/27 | 9/7/7/5 |
| source:confluence+google_drive | 2 | retrieval=2 | 16/8/0 | 0/0/0/0 |
| source:confluence+jira | 2 | citation=1, retrieval=1 | 19/5/0 | 1/1/1/0 |
| source:google_drive | 14 | citation=1, passed=7, retrieval=6 | 143/25/0 | 8/8/8/7 |
| source:jira | 20 | passed=13, product_runtime=2, retrieval=5 | 206/24/10 | 13/13/13/13 |
| type:basic | 21 | citation=1, passed=14, product_runtime=1, retrieval=4, selection=1 | 229/21/2 | 17/16/16/14 |
| type:completeness | 4 | passed=1, product_runtime=2, retrieval=1 | 30/8/10 | 1/1/1/1 |
| type:conflicting_info | 2 | retrieval=2 | 16/8/0 | 0/0/0/0 |
| type:constrained | 8 | citation=1, passed=2, product_runtime=4, retrieval=1 | 63/13/20 | 3/3/3/2 |
| type:intra_document_reasoning | 2 | citation=1, passed=1 | 23/1/0 | 2/2/2/1 |
| type:miscellaneous | 3 | passed=2, product_runtime=1 | 29/2/5 | 2/2/2/2 |
| type:project_related | 2 | retrieval=2 | 16/8/0 | 0/0/0/0 |
| type:semantic | 18 | passed=5, retrieval=12, selection=1 | 165/51/0 | 6/5/5/5 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
