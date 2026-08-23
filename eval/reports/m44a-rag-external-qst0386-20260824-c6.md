# Phase 4 RAG E2E Eval Report

- run_id: `m44a-rag-external-qst0386-20260824-c6`
- artifact_identity: `0a5bc40a8514177d30fef6d49375d4edead1635fe178115a98d7b388d14c9647`
- Gate: **passed**
- required: passed=12 / failed=0 / not_observed=0

## Failure Funnel

| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |
|---|---:|---|---:|---:|---:|---:|---|
| qst_0386 | 1 | rag/completed/complete/passed | 5 | 3 | 3 | 1 | passed |

## Assertion Views

| kind | eligible | passed | failed | not_observed |
|---|---:|---:|---:|---:|
| required | 12 | 12 | 0 | 0 |
| advisory | 3 | 2 | 1 | 0 |

## External Strata Outcomes

| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |
|---|---:|---|---|---|
| cardinality:single_document | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| difficulty:core | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| partition:external_dev | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| source:confluence | 1 | passed=1 | 12/0/0 | 1/1/1/1 |
| type:constrained | 1 | passed=1 | 12/0/0 | 1/1/1/1 |

## Interpretation Boundary

- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。
- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。
- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。
- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。
