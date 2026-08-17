# M39 P6 RAG Subgraph Readiness Audit

> 本报告只复盘已完成的 M34 artifact；没有调用 Knowledge Tool、AnswerFlow 或外部 provider。

## 输入闭合

- audit identity: `324ec7f8f4c7d4edf81bc73dc638905000d08d22861b079d26ebbaabc4b726c6`
- split identity: `f8164d3f57fe4c262f3a8f7ecd293196748d2abcbd4f387f3fbb8f50208138dd`
- profile identity: `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2`
- lexical retrieval: `knowledge-enterprise-sqlite-lexical-v1::fts5-unicode61-or-bm25-dedup-physical-v1`
- semantic retrieval: `knowledge-enterprise-milvus-semantic-v1::qwen-dense-cosine-dedup-physical-v1`
- answer Composer: `rag-qwen-evidence-support-nonthinking-unbounded-v4`
- dev / held-out: `60 / 120`
- provider calls: `0`

## Dev failure taxonomy

| 主层 | Scenario 数 |
| --- | ---: |
| `composer_support_gap` | 10 |
| `context_selection_or_packing_gap` | 13 |
| `not_classifiable` | 24 |
| `provider_unavailable` | 2 |
| `retrieval_candidate_gap` | 11 |

## P6 entrance conditions

| 条件 | 结论 | 证据 / 缺口 |
| --- | --- | --- |
| `reproducible_non_provider_failure_cluster` | `met` | dev 中有 24 个 retrieval/context 主层 Scenario |
| `observation_driven_new_evidence_action` | `not_met` | 现有 artifact 只记录一次固定 retrieval，没有任何第二动作的新增 Evidence 证据；缺口：尚未验证由首次 Observation 选择、且能新增 Evidence 的允许动作 |
| `dev_and_unpolluted_held_out_protocol` | `met` | 60/120 split 闭合；本审计只分类 dev，held-out 只做 identity 校验 |
| `comparable_extra_budget` | `not_met` | 已有单轮 latency/call/token 基线，但没有第二动作或父子预算定义；缺口：无法比较额外调用、延迟、出站与调试成本 |

## Decision

- recommendation: `no_go`
- `no_go` 表示当前保持确定性 lexical Pipeline 默认；它不等于永不优化 RAG。
- 只有新的 dev 证据证明 Observation 驱动动作能新增 Evidence，并冻结可比预算和未污染 held-out 后，才能另行规划 M40。
