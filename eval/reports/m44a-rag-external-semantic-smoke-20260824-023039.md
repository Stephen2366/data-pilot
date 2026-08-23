# Phase 4 RAG E2E Eval Report

- run_id: `m44a-rag-external-semantic-smoke-20260824-023039`
- artifact_identity: `4bfff9dffdf57ca667bbfa1f585eb287b37ff5de3d6dd9d32c49628c00d5346d`
- Gate: **failed**
- required: passed=92 / failed=16 / not_observed=0

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0016 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0047 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0019 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0386 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0461 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |
| qst_0181 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0420 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | retrieval |
| qst_0431 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 2 | passed |
| qst_0318 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 108 | 92 | 16 | 0 |
| advisory | 27 | 18 | 9 | 0 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:multi_document | 2 | passed=1, retrieval=1 | 20/4/0 | 1/1/1/1 |
| cardinality:single_document | 7 | passed=4, retrieval=3 | 72/12/0 | 4/4/4/4 |
| difficulty:basic | 3 | passed=1, retrieval=2 | 28/8/0 | 1/1/1/1 |
| difficulty:core | 3 | passed=2, retrieval=1 | 32/4/0 | 2/2/2/2 |
| difficulty:hard | 3 | passed=2, retrieval=1 | 32/4/0 | 2/2/2/2 |
| partition:external_dev | 9 | passed=5, retrieval=4 | 92/16/0 | 5/5/5/5 |
| source:confluence | 3 | passed=2, retrieval=1 | 32/4/0 | 2/2/2/2 |
| source:confluence+google_drive | 1 | retrieval=1 | 8/4/0 | 0/0/0/0 |
| source:google_drive | 2 | passed=1, retrieval=1 | 20/4/0 | 1/1/1/1 |
| source:jira | 3 | passed=2, retrieval=1 | 32/4/0 | 2/2/2/2 |
| type:basic | 3 | passed=1, retrieval=2 | 28/8/0 | 1/1/1/1 |
| type:completeness | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:conflicting_info | 1 | retrieval=1 | 8/4/0 | 0/0/0/0 |
| type:constrained | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:intra_document_reasoning | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:miscellaneous | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:semantic | 1 | retrieval=1 | 8/4/0 | 0/0/0/0 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
