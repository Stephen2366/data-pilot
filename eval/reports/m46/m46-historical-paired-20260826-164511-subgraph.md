# Phase 4 RAG E2E Eval Report

- run_id: `m46-historical-paired-20260826-164511-subgraph`
- artifact_identity: `578db71837669bcf4dd30fada21d28030d5ff7a319fba3f3c7ef24714e83ab42`
- Gate: **failed**
- required: passed=393 / failed=139 / not_observed=188

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0016 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0019 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0022 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0023 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0029 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0031 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0045 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0047 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0050 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0059 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0062 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0079 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0086 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0091 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0116 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0117 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0118 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0122 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0151 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0155 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0157 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0181 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0186 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0198 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0199 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0200 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0211 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0215 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0216 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0233 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0236 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0248 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0252 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0268 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0272 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0279 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0282 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0283 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0289 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0318 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0338 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0341 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0353 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0384 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0386 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0387 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0388 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0389 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0393 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0400 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0408 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0420 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0428 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0431 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0433 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0442 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0447 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0457 | 1 | rag/failed/no_answer/passed | 3 | 3 | 3 | 0 | product_runtime |
| qst_0461 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0462 | 1 | rag/external_unavailable/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 720 | 393 | 139 | 188 |
| advisory | 180 | 0 | 154 | 26 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:multi_document | 12 | product_runtime=12 | 78/38/28 | 2/2/2/0 |
| cardinality:single_document | 48 | product_runtime=48 | 315/101/160 | 9/9/9/0 |
| difficulty:basic | 21 | product_runtime=21 | 141/43/68 | 5/5/5/0 |
| difficulty:core | 25 | product_runtime=25 | 162/54/84 | 4/4/4/0 |
| difficulty:hard | 14 | product_runtime=14 | 90/42/36 | 2/2/2/0 |
| partition:external_dev | 60 | product_runtime=60 | 393/139/188 | 11/11/11/0 |
| source:confluence | 22 | product_runtime=22 | 144/62/58 | 4/4/4/0 |
| source:confluence+google_drive | 2 | product_runtime=2 | 12/8/4 | 0/0/0/0 |
| source:confluence+jira | 2 | product_runtime=2 | 12/6/6 | 0/0/0/0 |
| source:google_drive | 14 | product_runtime=14 | 93/25/50 | 3/3/3/0 |
| source:jira | 20 | product_runtime=20 | 132/38/70 | 4/4/4/0 |
| type:basic | 21 | product_runtime=21 | 141/43/68 | 5/5/5/0 |
| type:completeness | 4 | product_runtime=4 | 27/13/8 | 1/1/1/0 |
| type:conflicting_info | 2 | product_runtime=2 | 12/8/4 | 0/0/0/0 |
| type:constrained | 8 | product_runtime=8 | 54/16/26 | 2/2/2/0 |
| type:intra_document_reasoning | 2 | product_runtime=2 | 12/4/8 | 0/0/0/0 |
| type:miscellaneous | 3 | product_runtime=3 | 21/5/10 | 1/1/1/0 |
| type:project_related | 2 | product_runtime=2 | 12/8/4 | 0/0/0/0 |
| type:semantic | 18 | product_runtime=18 | 114/42/60 | 2/2/2/0 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
