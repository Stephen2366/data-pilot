# DataPilot Eval Baselines

> 本文是评测数字、分母、artifact、实验状态与可比性规则的唯一详细账本。`rag-current-state.md` 只保留 RAG 当前运行口径和结论摘要；两处出现同一 profile identity 时，以本文判断“能否比较”，以 `rag-current-state.md` 判断“当前运行使用什么”。M26 及以前的 formal / challenge / diagnostic 账本已归档到 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)。

更新时间：2026-08-26

## 当前状态

- **RAG 正式长期基线**：已登记 M34 EnterpriseRAG-Bench v1.0.0 external benchmark：36,417 documents / 139,214 units、60 diagnostic/dev + 120 held-out retrieval，以及同一 180 题集合的一次 completed Answer/Citation Eval。它与 22 条业务知识回归、M27 Text2SQL Eval 分账，不能混算。
- **当前 Text2SQL 合同**：`m27-v3`；延续 v2 的 `external_unavailable / not_observed` 语义，并把 Schema Context 的物理字段、metric key、输出 alias 分开静态校验；`orders_wide` 的业务月份统一按 `paid_at`，`snapshot_at/batch_id` 只表示快照版本。
- **当前 Text2SQL catalog**：28 个 Scenario；分类为 Core / Stress / Manual Lab。Smoke、Reliability、Database Exception 是 selector，不是复制题面的独立题集。
- **当前 Text2SQL 真实 LLM 基线**：尚未登记正式长期基线；现有真实运行均为 v2，只能作为修复前过渡证据，不能与 v3 直接比较。该结论不适用于上方已经登记的 M34 RAG 真实 Qwen Answer Eval。
- **默认运行配置**：仍以 [runbook.md](runbook.md) 为准；M27 没有切换模型、检索、embedding、数据库、oracle、timeout 或 retry。
- **M38 Hybrid 合同**：`phase4-harness-hybrid-v1` 是独立 deterministic 控制/安全 artifact（5 Scenario / 25 required），不与 M27 或 M34 的真实质量/长期数字混算；完整能力边界见 `rag-current-state.md` 和 Phase 4 changelog。
- **M39 P6 readiness audit**：只读取六份冻结 M34 输入并校验 SHA-256 / identity / split / runtime；它不是新的 retrieval 或 Answer Eval，也不新增质量基线。audit `324ec7f8...b726c6` 的严格 `no_go`、dev 分层计数与重开缺口见 [`m39-p6-readiness.md`](../../eval/reports/m39-p6-readiness.md)。
- **M40 P7 technical assurance**：`phase4-assurance-v1` 是九个现有 deterministic family 的 closed-world 技术 Gate，另以 `phase4-trace-rehearsal-v1` 关联 SQL、RAG、Hybrid、澄清恢复和安全拒绝的同次 API/Trace 安全投影。它只登记 contract/artifact identity 与 P6 verified `no_go`，不产生新的质量分数、不混入 M27/M34 数字，也不等于 Phase 4 人工验收或生产就绪。
- **M41 business RAG 产品 Eval**：当前合同为 `phase4-rag-e2e-v1`，用户入口已合并为唯一 `business` selector（5 题各 1 次），并保留 `--scenario` 单题诊断。首次真实 Qwen Smoke `m41-rag-smoke-20260822-01` 是合并前的历史 2 题 artifact，已 completed 且 review 通过；原件不改签，也不能冒充当前 5 题 Business 结果。
- **M41 external 套件与候选对比**：完整 180 catalog 的 difficulty 为 basic/core/hard `64/74/42`，与 dev/held-out partition、smoke/basic/core/hard/reliability/full suite 分离。compare-v2 默认只作同 runtime strict repeat；候选 A/B 必须显式声明允许变化的 runtime 字段，自动 paired 迁移仍不等于人工 correctness。现有 v2/post-fix dev smoke/basic/core 快照见下方，正式长期基线尚未登记。
- **M42 Phase 4B B0 Eval 前置**：`phase4b-agent-scenario-v1` 只冻结 sequence/turn/execution/assertion closed-world skeleton 和 capability handoff；deterministic rehearsal 的 Agent artifact `b303d4d...52982`、business Observation `e6bc5fa...aab99` 与 reserve `f70c5fc...e505` 都不是新的质量分数或正式长期基线。reserve为60题`20/20/20`；M46因historical no-go未冻结candidate、未解封或运行该reserve，当前仍sealed/read0。M41/M34 artifact不改签。
- **M43 Phase 4B B1 deterministic artifact**：新增 additive `phase4b-agent-scenario-artifact-v2`，只记录 TaskDelta、state transition、Evidence validity、node Context、task lifecycle 与 0/1 invocation 事实；M42 v1 未改签。当前 rehearsal artifact `cc9f696...b27c92` 绑定 B1 contract `383fbf5...e9d32`，8 项 deterministic checks 通过、external calls 为 0。它证明 B1 技术合同和冻结 oracle，不是 LLM/Agent 质量分数或正式长期基线；M46 reserve 仍 sealed。
- **M44A Enterprise semantic 技术 smoke**：产品 API/external Eval 默认改为 semantic，但 M34 lexical/semantic 正式 retrieval 结果和历史 artifact 不改签。单题 C6 `m44a-rag-external-qst0386-20260824-c6` 只证明真实向量产品链闭合，不自动登记正式长期基线，也不构成 lexical/semantic A/B。
- **M44A semantic dev Smoke**：9 题 post-fix external smoke `m44a-rag-external-semantic-smoke-20260824-023039` 已 completed；Gate `92/16/0`、人工 `2/7`。与历史 lexical smoke 的 candidate compare 已按预注册 runtime 字段闭合，但单次 generation 不构成 Reliability 或单组件因果；仍不登记正式长期基线。
- **M44 Agent Scenario v3**：`phase4b-agent-scenario-v3` 是 B2 closed-world deterministic 控制/安全 artifact；rehearsal identity `63c9483c8d55b958b48925085d99c9bb14164c1120a7d364c0b1c611dabac700`，6/6 checks、external calls=0。它冻结 action sequence、actual consumption、EvidenceDelta/progress/termination、Context 与 private-payload 安全投影，不产生真实模型/RAG 质量分数，不与 M27/M34/M41 基线混算。
- **M46 historical paired v2**：external `diagnostic_dev/full` 60 题的 Pipeline/Subgraph 两臂均 completed，run `m46-historical-paired-20260826-160237`，Gate `571/112/37 → 375/126/219`，60 个 paired verdict 全部 insufficient，Subgraph 60 题最终均 no-answer，因此是不可变的 `no-go/revise` 开发历史，不是正式长期基线或 reserve 决策。Pipeline 已知 `113 requests / 132841 chat tokens`；Subgraph 仅有下限 `123 / 102522`，3 条 child projection 缺失且 embedding tokens 不可得。后续 v3 是独立candidate与独立授权，不能混算或覆盖v2；sealed reserve始终未解封。
- **M46 historical paired v3（当前最终 historical 结论）**：run `m46-historical-paired-20260826-164511` 两臂各60 completed，Gate `598/112/10 → 393/139/188`，paired `57 insufficient / 3 tie`，Subgraph仍为`60/60 no_answer`。v3修复了value-shape与projection完整性，answer-ready增至26，但全部被Composer合同拒绝，另有19个Evidence run mismatch；结论=`no_go_revise_stop`，不登记长期基线、不冻结candidate、不解封reserve。已知requests `120→139`、chat tokens `133581→110622`，embedding token不可得；详见 [`closed-set review`](../../eval/reports/m46/m46-historical-paired-20260826-164511-review.md)。
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
- M41 completed run 的 strict repeat 只在 catalog/selector/replicate、assertion plan/scorer、Scenario metadata 与完整 resolved runtime 相同时成立。compare-v2 的候选模式仍要求前述非 runtime 条件全部相同，并只放行 `--allow-runtime-difference` 预注册字段；未声明漂移失败关闭。多个允许字段只能解释整体候选，不能做单组件因果归因；paired assertion/失败层/usage/latency 与人工语义 verdict 并列，不互相替代。

### 人工复核的边界

M27 review bundle 是解释自动结果的旁路证据，不是第二套分数：它不改变 `eligible / observed / passed / failed / not_observed`、不改变 Gate，也不能与自动数字混算。Core / Stress 后复核全部自动失败、退款/SCD/金额/时间/递归等高风险合同，并抽样少量自动通过题。

自 `m27-review-bundle-v2` 起，bundle 保存 artifact 与各 checkpoint 的 SHA-256，复核前可验证来源仍是原文件。普通业务题没有 candidate SQL 时只能记为 `insufficient_evidence`；安全或预期拒绝题可以凭明确拦截证据判通过。人工分类只服务于错误聚合，绝不成为新分母或 Gate 输入。早期 v1 review 是无哈希的历史旁路材料，不能直接和 v2 的来源校验混用。

M41 `phase4-rag-e2e-review-v1` 同样绑定 artifact 与逐 execution checkpoint SHA-256，并以 `<scenario-id>:r<replicate>` 闭集接收 `pass/fail/insufficient_evidence`。它必须复核自动失败/`not_observed`、高风险/多文档题和通过抽样；deterministic required terms 只是 correctness/completeness 下限。M41 未启用 LLM Judge，人工 verdict 与自动 Gate 永远并列而不互改。

## 当前有效实验快照

这里保留仍能帮助判断当前路线的真实运行；它们未必已成为正式长期 baseline，也未必能作严格对照。每条都必须写清楚证据状态和解释边界。Smoke、运行事故、中断和外部服务异常不作为独立记录进入本账本。

### M47 Agent Scenario v5 durable control artifact（2026-08-26）

- additive `phase4b-agent-scenario-v5` 覆盖 `RESTART_RESUME / MULTIWORKER_CONFLICT / WRONG_OWNER / EXPIRED / CLEAR / SWITCH` 六类 durable task control/safety 场景，v1～v4 保持 `unchanged_readable`。
- 最终零 provider rehearsal 6/6 完成，artifact identity `c1ad166376db7ecc4e49b6aa870b4967c37d0f0779eeeb521fe7daf9d66000af`，calls/tokens=`0/0`，报告 `eval/reports/m47/m47-agent-scenario-v5-rehearsal.json`。真实 MySQL P1/P2 也均为 `continue`，但属于开发期 exploratory/baseline-ineligible Probe。
- 这组证据证明 durable lifecycle、CAS、安全投影与兼容合同可复演，不评价 Agent 答案正确率、RAG 质量、吞吐或 Reliability；未登记正式长期质量基线，也不需要为 B5 追加付费 Formal Eval。

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
| Retrieval lexical | 2026-08-16 | `enterprise-rag-retrieval-eval-v1`；SQLite FTS5 lexical；`enterprise-unit-paragraph-2400-v1`；@20 | dev coverage/all-gold/MRR `0.810417 / 0.766667 / 0.645303`；held-out `0.823125 / 0.775000 / 0.723134` | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | 历史正式 retrieval 锚点；M44A 不改签。只证明 gold 文档召回，不证明回答正确。 |
| Retrieval semantic candidate | 2026-08-16 | 同 corpus/split/@20；Milvus semantic `9aec12c8...e20` | dev `0.737500 / 0.700000 / 0.621421`；held-out `0.773958 / 0.741667 / 0.630477` | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | 两个 split 均未胜 lexical；M44A 后成为产品默认是用户确认的运行合同，不是质量胜出结论。 |
| Answer / Citation full | 2026-08-16 | `enterprise-rag-answer-eval-v1`；当时的 lexical 产品默认；Qwen Composer `rag-qwen-evidence-support-nonthinking-unbounded-v4`；180 题 | complete `146/180`；all-gold cited `80/180`；mean gold coverage `49.3981%`；multi-document all-gold `2/38`；semantic all-gold `15/52`；10 unavailable；24 support contract rejected；405,305 tokens | [完整 identity / SHA-256](../../eval/reports/m34-enterprise-rag-baseline-manifest.md) | completed 证明当时 lexical 链路和账本可复现，不证明自然答案正确率或当前 semantic 产品质量；本地大 artifact 不提交 Git。 |

可提交的轻量证据清单为 [`eval/reports/m34-enterprise-rag-baseline-manifest.md`](../../eval/reports/m34-enterprise-rag-baseline-manifest.md)，保存五个 completed artifact 的完整 identity、文件 SHA-256、共同运行身份和关键结果。原始大 JSON 仍只保存在 `.agent_work/temp/`，不是唯一长期事实源；详细失败结构与运行边界见 `rag-current-state.md`。

### RAG：M41 business product E2E

| Run ID | 日期 | Selector / Scenario | Protocol / runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|
| [`m41-rag-smoke-20260822-01`](../../eval/reports/m41-rag-artifacts/m41-rag-smoke-20260822-01.json) | 2026-08-22 | Smoke；2 Scenario / 2 physical executions | `phase4-rag-e2e-v1`；business release `7d0d0937...409a`；lexical；Qwen `qwen3.7-plus`；eval-only outbound；60s/retry0 | [report](../../eval/reports/m41-rag-smoke-20260822-01.md)：required `23 passed / 0 failed / 0 not_observed`；Gate `passed`；人工 review `2 pass` | 当前有效首次 Smoke 快照，不是正式长期基线。唯一 generation 成功，usage `660 + 352 = 1012` tokens；no-candidate 题零 provider。只证明两个窄场景，不外推 Core、多文档或 Reliability。 |

### RAG：M41 external 180 分层产品链路

| Run ID | 日期 | Partition / 分层 | Protocol / runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|
| [`m41-rag-external-dev-20260822-01`](../../eval/reports/m41-rag-external-artifacts/m41-rag-external-dev-20260822-01.json) | 2026-08-23 | 冻结 dev 60；保留 question type / source / document cardinality | M41 external catalog + fixed-RAG eval route + 产品 Harness/RAG Tool + M34 lexical profile + Qwen `qwen3.7-plus`；60s/retry0 | [report](../../eval/reports/m41-rag-external-dev-20260822-01.md)：required `524 passed / 136 failed / 0 not_observed`，Gate `failed`；triage `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`；人工 review `18 pass / 26 fail / 16 insufficient_evidence`；usage `137299` tokens | **pre-fix candidate，不是正式长期基线**。运行后发现 5 个 Composer 坏结构被误分为 Harness failure；原 artifact 不改签、不重跑，当前代码已修正未来分类并新增 assertion，因此不能与未来新 run 直接作同协议比较。120 held-out 未运行；exact-fact `0/60` 只是字符串下限，不是语义正确率。 |
| [`m41-rag-external-core-20260823-151649`](../../eval/reports/m41-rag-external-artifacts/m41-rag-external-core-20260823-151649.json) | 2026-08-23 | dev core 25（difficulty=core） | M41 external catalog v2 + fixed-RAG eval route + 产品 Harness/RAG Tool + M34 lexical profile + Qwen `qwen3.7-plus`；60s/retry0 | [report](../../eval/reports/m41-rag-external-core-20260823-151649.md)：required `211 passed / 58 failed / 31 not_observed`，Gate `failed`；triage `9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`；AI reviewer verdict `4 pass / 13 fail / 8 insufficient_evidence`；usage `53106 tokens` | 首条 post-fix dev core 快照，未登记正式基线。5 题 Composer 坏结构如实标记（归类修正生效）；9 题 lexical 漏召回为最大失败层；verdict fail 主体是检索错文档→答偏与有引用仍拒答；自动 Gate 通过的 6 题中 2 题 verdict 仍 fail。120 held-out 未运行。 |
| [`m41-rag-external-smoke-20260823-154101`](../../eval/reports/m41-rag-external-artifacts/m41-rag-external-smoke-20260823-154101.json) | 2026-08-23 | dev smoke 9（basic/core/hard 各 3） | 同上；9 executions | [report](../../eval/reports/m41-rag-external-smoke-20260823-154101.md)：required `96 passed / 12 failed / 0 not_observed`，Gate `failed`；triage `4 passed / 2 selection / 2 citation / 1 retrieval`；AI reviewer verdict `3 pass / 6 fail`；usage `20288 tokens` | post-fix 快速质量快照，未登记基线。9 题均形成答案但只有 3 题语义通过；自动 triage passed 的 qst_0318 因日期错误被判 fail，证明自动断言仍只是下限。 |
| [`m41-rag-external-basic-20260823-154101`](../../eval/reports/m41-rag-external-artifacts/m41-rag-external-basic-20260823-154101.json) | 2026-08-23 | dev basic 21 | 同上；21 executions | [report](../../eval/reports/m41-rag-external-basic-20260823-154101.md)：required `215 passed / 25 failed / 12 not_observed`，Gate `failed`；triage `12 passed / 4 retrieval / 3 product_runtime / 1 selection / 1 citation`；AI reviewer verdict `9 pass / 9 fail / 3 insufficient_evidence`；usage `47814 tokens` | post-fix dev basic 快照，未登记基线。3 个 insufficient 均为 provider 有响应但 Composer 结构合同失败；其余 fail 集中在错材料/漏召回后答偏或关键事实缺失。与 Smoke 重叠 3 题 verdict 一致，但不能冒充 Reliability。 |

M44A 另有一条**当前技术 smoke 证据**：[`m44a-rag-external-qst0386-20260824-c6`](../../eval/reports/m41-rag-external-artifacts/m44a-rag-external-qst0386-20260824-c6.json) 只执行 `diagnostic_dev/qst_0386` 一次。其 [report](../../eval/reports/m44a-rag-external-qst0386-20260824-c6.md) required `12 passed / 0 failed / 0 not_observed`、Gate `passed`，semantic 漏斗 `5→3→3→1`，Qwen usage `2054` tokens，人工语义 verdict `pass`；自动 advisory `answer_facts_exact_lower_bound` 失败并保留。artifact identity `0a5bc40a8514177d30fef6d49375d4edead1635fe178115a98d7b388d14c9647`。它没有 lexical 配对、没有 Reliability、没有运行 60 dev 或 120 held-out，因此不是正式长期基线，也不能证明 semantic 质量优于 lexical。

随后按独立用户授权执行 semantic external dev Smoke：[`m44a-rag-external-semantic-smoke-20260824-023039`](../../eval/reports/m41-rag-external-artifacts/m44a-rag-external-semantic-smoke-20260824-023039.json)，9/9 execution completed、Gate failed、required `92/16/0`、triage `5 passed / 4 retrieval`、usage `19033` tokens；[人工 review](../../eval/reports/m44a-rag-external-semantic-smoke-20260824-023039-reviewed.json) 为 `2 pass / 7 fail`。与历史 lexical smoke 的 [candidate compare](../../eval/reports/m44a-rag-external-semantic-smoke-vs-lexical-20260824-compare.json) 为自动 `1 win / 5 tie / 3 loss`、人工 `3/6→2/7`、tokens `20288→19033`。两侧都只有每题一次 generation，compare 同时放行完整 semantic runtime 字段，因此不能推导稳定性或单组件因果；本 run 不登记正式长期基线，120 held-out 未运行。

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
