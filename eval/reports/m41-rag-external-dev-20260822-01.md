# Phase 4 RAG E2E Eval Report

- run_id: `m41-rag-external-dev-20260822-01`
- artifact_identity: `ad1bcd7694d3b76b69748146a08107de7e7741c4cf7e59885bcc625251bf597b`
- Gate: **failed**
- required: passed=524 / failed=136 / not_observed=0

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
| qst_0086 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0091 | 1 | rag/failed/no_answer/passed | 5 | 3 | 3 | 0 | product_runtime |
| qst_0116 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0117 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0118 | 1 | none/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0122 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0151 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0155 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0157 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0181 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0186 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0198 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0199 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0200 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0211 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0215 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0216 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0233 | 1 | none/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0236 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0248 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0252 | 1 | rag/failed/no_answer/passed | 5 | 3 | 3 | 0 | product_runtime |
| qst_0268 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0272 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0279 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0282 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0283 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0289 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0318 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0338 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0341 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0353 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0384 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0386 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0387 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0388 | 1 | none/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0389 | 1 | none/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0393 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | citation |
| qst_0400 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0408 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0420 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | citation |
| qst_0428 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0431 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | selection |
| qst_0433 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 3 | retrieval |
| qst_0442 | 1 | none/failed/no_answer/passed | 0 | 0 | 0 | 0 | product_runtime |
| qst_0447 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | retrieval |
| qst_0457 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0461 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0462 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 660 | 524 | 136 | 0 |
| advisory | 180 | 106 | 74 | 0 |

## External Strata

| stratum | questions |
|---|---:|
| cardinality:multi_document | 12 |
| cardinality:single_document | 48 |
| partition:external_dev | 60 |
| source:confluence | 22 |
| source:confluence+google_drive | 2 |
| source:confluence+jira | 2 |
| source:google_drive | 14 |
| source:jira | 20 |
| type:basic | 21 |
| type:completeness | 4 |
| type:conflicting_info | 2 |
| type:constrained | 8 |
| type:intra_document_reasoning | 2 |
| type:miscellaneous | 3 |
| type:project_related | 2 |
| type:semantic | 18 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
