# DataPilot Eval Baselines

> 本文是评测数字、分母、artifact、实验状态与可比性规则的唯一详细账本。`rag-current-state.md` 只保留 RAG 当前运行口径和结论摘要；两处出现同一 profile identity 时，以本文判断“能否比较”，以 `rag-current-state.md` 判断“当前运行使用什么”。M26 及以前的 formal / challenge / diagnostic 账本已归档到 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)。

更新时间：2026-08-22

## 当前状态

- **RAG 正式长期基线**：已登记 M34 EnterpriseRAG-Bench v1.0.0 external benchmark：36,417 documents / 139,214 units、60 diagnostic/dev + 120 held-out retrieval，以及同一 180 题集合的一次 completed Answer/Citation Eval。它与 22 条业务知识回归、M27 Text2SQL Eval 分账，不能混算。
- **当前 Text2SQL 合同**：`m27-v3`；延续 v2 的 `external_unavailable / not_observed` 语义，并把 Schema Context 的物理字段、metric key、输出 alias 分开静态校验；`orders_wide` 的业务月份统一按 `paid_at`，`snapshot_at/batch_id` 只表示快照版本。
- **当前 Text2SQL catalog**：28 个 Scenario；分类为 Core / Stress / Manual Lab。Smoke、Reliability、Database Exception 是 selector，不是复制题面的独立题集。
- **当前 Text2SQL 真实 LLM 基线**：尚未登记正式长期基线；现有真实运行均为 v2，只能作为修复前过渡证据，不能与 v3 直接比较。该结论不适用于上方已经登记的 M34 RAG 真实 Qwen Answer Eval。
- **默认运行配置**：仍以 [runbook.md](runbook.md) 为准；M27 没有切换模型、检索、embedding、数据库、oracle、timeout 或 retry。
- **M38 Hybrid 合同**：`phase4-harness-hybrid-v1` 是独立 deterministic 控制/安全 artifact（5 Scenario / 25 required），不与 M27 或 M34 的真实质量/长期数字混算；完整能力边界见 `rag-current-state.md` 和 Phase 4 changelog。
- **M39 P6 readiness audit**：只读取六份冻结 M34 输入并校验 SHA-256 / identity / split / runtime；它不是新的 retrieval 或 Answer Eval，也不新增质量基线。audit `324ec7f8...b726c6` 的严格 `no_go`、dev 分层计数与重开缺口见 [`m39-p6-readiness.md`](../../eval/reports/m39-p6-readiness.md)。
- **M40 P7 technical assurance**：`phase4-assurance-v1` 是九个现有 deterministic family 的 closed-world 技术 Gate，另以 `phase4-trace-rehearsal-v1` 关联 SQL、RAG、Hybrid、澄清恢复和安全拒绝的同次 API/Trace 安全投影。它只登记 contract/artifact identity 与 P6 verified `no_go`，不产生新的质量分数、不混入 M27/M34 数字，也不等于 Phase 4 人工验收或生产就绪。
- **M41 business RAG 产品 Eval**：当前合同为 `phase4-rag-e2e-v1`，使用 business 22-entry release，经 `/api/query` 产品 Harness 一题一次执行，并提供 funnel/Gate/triage/review/compare。首次真实 Qwen Smoke `m41-rag-smoke-20260822-01` 已 completed，自动 Gate 与逐题人工 review 均通过；它是当前有效实验快照，不是正式长期基线，也不得拿 M34 external 或 M31–M40 deterministic artifact 与其混算。
- **记录分类**：实验先按“是否仍能支持当前路线判断”进入「当前有效实验快照」；用户明确指定后才进入「正式长期基线」；合同、运行条件或决策价值已过时的记录转入「历史实验记录」。分类不按模块编号自动新增标题。

## 读数与分母

报告按 assertion kind 展示以下事实：

| 字段 | 含义 |
|---|---|
| `eligible` | 该 Scenario 声明了这种 assertion。 |
| `observed` | 有足够证据完成自动判断，即 `passed + failed`。 |
| `passed` / `failed` | 已观察到的自动断言结果。 |
| `not_observed` | 声明了 assertion，但因 pipeline error、external unavailable、缺 evidence 等原因不能自动判断。 |
| `unavailable` | `not_observed` 中 `external_unavailable` 的原因切片，不额外加入分母，也不等同 semantic wrong。 |

固定关系：`eligible = passed + failed + not_observed`，`observed = passed + failed`。自动能力率只在 observed 集合中计算：`passed / (passed + failed)`。

Gate 也是独立视图：selector / suite policy 决定 assertion 为 `required`、`advisory` 或 `excluded`，projector 再推导 `passed`、`failed` 或 `inconclusive`。Reliability 的多个 replicate 会归约为同一个逻辑 Scenario / assertion，不扩大业务问题分母。

上句是 M27 Text2SQL 的归约口径。M41 v1 的 report/Gate 保留每个 `<scenario-id>:r<replicate>` assertion cell，并显式展示 replicate；比较 M41 Reliability 时不得把物理 cell 分母与 M27 的逻辑 Scenario 分母混算。

## 可比性规则

- 只比较相同的 `contract_version`、selected contract hash、suite policy hash、execution protocol、oracle fixture 和 resolved runtime identity 的 M27 EvalRun。
- 修改 canonical Scenario、reference SQL、typed assertion、selector、gate、模型、检索、embedding、数据库 snapshot 或 reliability protocol 后，必须标记为新合同/新条件，不能把结果直接拼进同一基线序列。
- retrieval-only benchmark 继续独立记录；它不调用 PipelinePort，不能证明端到端 Text2SQL 收益。
- M34 RAG 只在 dataset / question set / split / profile / parser / unit recipe / top-k 与评分口径一致时比较；adapter、embedding、Composer、context budget 或 support/citation 合同变化必须以新 identity 形成候选，不得覆盖本基线。
- M34 retrieval 与 Answer/Citation 是两层证据：retrieval gold coverage 不能冒充答案正确率；`answer_status=complete` 只表示回答及引用合同闭合，也不能冒充 correctness。M34 未启用 LLM Judge。
- M41 completed run 只在 catalog/selector/replicate、assertion plan/scorer、business release/corpus、retrieval adapter/recipe、Composer/model/provider、release + generation outbound policy、caller fixture 与 timeout/retry 全部相同时严格 compare；当前 compare 拒绝任何 identity 漂移，不提供跨候选升降解释。

### 人工复核的边界

M27 review bundle 是解释自动结果的旁路证据，不是第二套分数：它不改变 `eligible / observed / passed / failed / not_observed`、不改变 Gate，也不能与自动数字混算。Core / Stress 后复核全部自动失败、退款/SCD/金额/时间/递归等高风险合同，并抽样少量自动通过题。

自 `m27-review-bundle-v2` 起，bundle 保存 artifact 与各 checkpoint 的 SHA-256，复核前可验证来源仍是原文件。普通业务题没有 candidate SQL 时只能记为 `insufficient_evidence`；安全或预期拒绝题可以凭明确拦截证据判通过。人工分类只服务于错误聚合，绝不成为新分母或 Gate 输入。早期 v1 review 是无哈希的历史旁路材料，不能直接和 v2 的来源校验混用。

M41 `phase4-rag-e2e-review-v1` 同样绑定 artifact 与逐 execution checkpoint SHA-256，并以 `<scenario-id>:r<replicate>` 闭集接收 `pass/fail/insufficient_evidence`。它必须复核自动失败/`not_observed`、高风险/多文档题和通过抽样；deterministic required terms 只是 correctness/completeness 下限。M41 未启用 LLM Judge，人工 verdict 与自动 Gate 永远并列而不互改。

## 当前有效实验快照

这里保留仍能帮助判断当前路线的真实运行；它们未必已成为正式长期 baseline，也未必能作严格对照。每条都必须写清楚证据状态和解释边界。Smoke、运行事故、中断和外部服务异常不作为独立记录进入本账本。

> 2026-08-10 注：下表均为 `m27-v2` 修复前快照。它们仍可解释当时的模型行为和 M28 问题来源，但已不属于 `m27-v3` 可比序列；本轮未运行真实 LLM Eval。

| 类型 | 证据状态 | Run ID | 日期 | 协议 / resolved runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|---|
| Core | 过渡证据 | [`m27-core-20260809-qwen37plus-milvus-02`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-milvus-02.json) | 2026-08-09 | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off；19 logical / 19 physical | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-milvus-02.md)；required：28 passed / 0 failed / 6 not_observed；Gate `inconclusive` | 两个 QueryPlan timeout（商品 Top5、商品退款率排名）没有 candidate SQL，各贡献 3 条 external unavailable。该 run 早于 artifact 补齐 collection / embedding / corpus 字段：可用于解释 P0/P1 首轮结果，但不是严格 Milvus / P1 对照，也未登记长期 baseline。 |
| Stress | 当前单轮证据 | [`m27-stress-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-stress-20260809-qwen37plus-milvus-01.json) | 2026-08-10 | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`；195 docs / hash `8a8b6626...`；45s / retry0；SQLite seed；9 / 9 | [Markdown report](../../eval/reports/m27-stress-20260809-qwen37plus-milvus-01.md)；全部 assertion：7 passed / 14 failed / 4 not_observed；7 completed / 2 external unavailable；required：0 / 0 / 0，Gate `inconclusive` | Stress 全为 advisory，不是硬门。单次样本；失败集中在渠道 GMV、金额对账、递归类目、价格历史、渠道退款率与 schema context，不能据此断言 Milvus 因果或登记长期 baseline。 |
| Database Exception | 当前单轮证据 | [`m27-database-exception-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-database-exception-20260809-qwen37plus-milvus-01.json) | 2026-08-10 | 同上；7 / 7 | [Markdown report](../../eval/reports/m27-database-exception-20260809-qwen37plus-milvus-01.md)；全部 assertion：4 passed / 4 failed / 11 not_observed；3 completed / 4 external unavailable；required：0 / 0 / 0，Gate `inconclusive` | 该 selector 从 Stress 复用异常业务 Scenario，但 policy 独立，不能与 Stress 混算。单次样本；外部不可用较多，未登记长期 baseline。 |

后续当前合同下的 Core、Stress、Reliability、Database Exception 在本表追加一行，不与不同 selector / suite 混算。记录失去当前决策价值后移入文末「历史实验记录」，不按 M28、M29 等模块编号新增同级标题。

## 正式长期基线登记

只有用户明确指定某条 completed run 后，才在这里登记为正式长期基线。

### RAG：M34 EnterpriseRAG-Bench external benchmark

共同身份：dataset `70c572328a90ec5dc380c086181af4d3706264f5aefd71c2856329f996d93cf7`；question set `9a21ca95995c9d2c9e962351e9e7485630233a89c280a5c928b6bc40b9cd271c`；split `f8164d3f57fe4c262f3a8f7ecd293196748d2abcbd4f387f3fbb8f50208138dd`；profile `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2`。业务 22 条 active release 保持独立，不属于本分母。

| 类型 | 日期 | 协议 / runtime | 结果 | Artifact | 解释边界 |
|---|---|---|---|---|---|
| Retrieval lexical | 2026-08-16 | `enterprise-rag-retrieval-eval-v1`；SQLite FTS5 lexical；`enterprise-unit-paragraph-2400-v1`；@20 | dev coverage/all-gold/MRR `0.810417 / 0.766667 / 0.645303`；held-out `0.823125 / 0.775000 / 0.723134` | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | 当前 external 默认与后续候选的正式锚点；只证明 gold 文档召回，不证明回答正确。 |
| Retrieval semantic candidate | 2026-08-16 | 同 corpus/split/@20；Milvus semantic `9aec12c8...e20` | dev `0.737500 / 0.700000 / 0.621421`；held-out `0.773958 / 0.741667 / 0.630477` | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | 两个 split 均未胜 lexical，故不激活；不代表 semantic、Hybrid 或 rerank 永久无价值。 |
| Answer / Citation full | 2026-08-16 | `enterprise-rag-answer-eval-v1`；lexical external 默认；Qwen Composer `rag-qwen-evidence-support-nonthinking-unbounded-v4`；180 题 | complete `146/180`；all-gold cited `80/180`；mean gold coverage `49.3981%`；multi-document all-gold `2/38`；semantic all-gold `15/52`；10 unavailable；24 support contract rejected；405,305 tokens | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | completed 证明真实链路和账本可复现，不证明自然答案正确率或生产质量；本地大 artifact 不提交 Git。 |

可提交的轻量证据清单为 [`eval/reports/m34-enterprise-rag-baseline-manifest.md`](../../eval/reports/m34-enterprise-rag-baseline-manifest.md)，保存五个 completed artifact 的完整 identity、文件 SHA-256、共同运行身份和关键结果。原始大 JSON 仍只保存在 `.agent_work/temp/`，不是唯一长期事实源；详细失败结构与运行边界见 `rag-current-state.md`。

### RAG：M41 business product E2E

| Run ID | 日期 | Selector / Scenario | Protocol / runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|
| [`m41-rag-smoke-20260822-01`](../../eval/reports/m41-rag-artifacts/m41-rag-smoke-20260822-01.json) | 2026-08-22 | Smoke；2 Scenario / 2 physical executions | `phase4-rag-e2e-v1`；business release `7d0d0937...409a`；lexical；Qwen `qwen3.7-plus`；eval-only outbound；60s/retry0 | [report](../../eval/reports/m41-rag-smoke-20260822-01.md)：required `23 passed / 0 failed / 0 not_observed`；Gate `passed`；人工 review `2 pass` | 当前有效首次 Smoke 快照，不是正式长期基线。唯一 generation 成功，usage `660 + 352 = 1012` tokens；no-candidate 题零 provider。只证明两个窄场景，不外推 Core、多文档或 Reliability。 |

### RAG：M41 external 180 分层产品链路

| Run ID | 日期 | Partition / 分层 | Protocol / runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|
| [`m41-rag-external-dev-20260822-01`](../../eval/reports/m41-rag-external-artifacts/m41-rag-external-dev-20260822-01.json) | 2026-08-23 | 冻结 dev 60；保留 question type / source / document cardinality | M41 external catalog + fixed-RAG eval route + 产品 Harness/RAG Tool + M34 lexical profile + Qwen `qwen3.7-plus`；60s/retry0 | [report](../../eval/reports/m41-rag-external-dev-20260822-01.md)：required `524 passed / 136 failed / 0 not_observed`，Gate `failed`；triage `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`；人工 review `18 pass / 26 fail / 16 insufficient_evidence`；usage `137299` tokens | **pre-fix candidate，不是正式长期基线**。运行后发现 5 个 Composer 坏结构被误分为 Harness failure；原 artifact 不改签、不重跑，当前代码已修正未来分类并新增 assertion，因此不能与未来新 run 直接作同协议比较。120 held-out 未运行；exact-fact `0/60` 只是字符串下限，不是语义正确率。 |

M34 180 题旧 artifact 另有零调用分层投影 [`m41-m34-180-layered-history.md`](../../eval/reports/m41-m34-180-layered-history.md)：它能回看 retrieval / Composer support / citation / answer 字符串下限，但 API、Router、Harness 与 selected/generation-visible 因旧证据未保存而标 `not_observed`，不得冒充产品 E2E。

### Text2SQL：M27

| Run ID | 日期 | Selector / Scenario | Protocol | Resolved runtime | Oracle / artifact | Assertion views | Gate | 解释边界 |
|---|---|---|---|---|---|---|---|---|
| *尚无* | — | — | — | — | — | — | — | 已有当前有效的 Core 过渡快照，但尚未由用户指定哪条 completed run 作为正式长期基线。 |

每条记录至少链接脱敏 EvalRun JSON 与 Markdown report；只引用 `ResolvedRuntimeIdentity`，不以命令行表象替代实际模型、检索和 oracle 事实。

## 历史实验记录

这里保存已经不能支撑当前路线判断、但仍值得追溯的实验。它们不参与当前升降比较，也不因后续模块新增而继续占用「当前有效实验快照」。

| 类型 | Run ID | 日期 | 协议 / resolved runtime | Assertion views / Gate | 转入历史的原因 |
|---|---|---|---|---|---|
| Core | [`m27-core-20260809-qwen37plus-local-01`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-local-01.json) | 2026-08-09 | Qwen `qwen3.7-plus`；inmemory deterministic / weighted；45s / retry0；SQLite seed；LangFuse off；19 logical / 19 physical | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-local-01.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | `m27-v1` 冻结快照；退款排名 3 条 failed 混入 timeout 空答卷投影，只保留给 P0 根因追溯，不能与 v2 比。 |
| Core | [`m27-core-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-milvus-01.json) | 2026-08-09 | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off；19 / 19 | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-milvus-01.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | `m27-v1` 冻结快照；195-doc clean collection、hash `8a8b6626...`；不能与 v2 比。 |
| Core | [`m27-core-20260809-qwen37max-local-06`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-local-06.json) | 2026-08-09 | Qwen `qwen3.7-max`；inmemory deterministic / weighted；45s / retry0；SQLite seed；LangFuse off；19 / 19 | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-local-06.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | `m27-v1` 冻结快照；单次样本不足以证明与 plus 等价，不能与 v2 比。 |
| Core | [`m27-core-20260809-qwen37max-milvus-02`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-milvus-02.json) | 2026-08-09 | Qwen `qwen3.7-max`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off；19 / 19 | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-milvus-02.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | `m27-v1` 冻结快照；195-doc clean collection、hash `8a8b6626...`；不能与 v2 比。 |
