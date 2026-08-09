# DataPilot Eval Baselines

> 本文记录当前 EvalRun 基线与可比性规则。M26 及以前的 formal / challenge / diagnostic 账本已归档到 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)。

更新时间：2026-08-09

## 当前状态

- **当前合同**：`m27-v2`；每个业务问题是一个 canonical Scenario，多个 typed assertion 共享一次执行证据。v2 将 QueryPlan timeout 等“没有候选答卷”的情况记为 `external_unavailable / not_observed`，不再伪装成业务 failed。
- **当前 catalog**：28 个 Scenario；分类为 Core / Stress / Manual Lab。Smoke、Reliability、Database Exception 是 selector，不是复制题面的独立题集。
- **当前真实 LLM 基线**：尚未登记正式长期基线。
- **默认运行配置**：仍以 [runbook.md](runbook.md) 为准；M27 没有切换模型、检索、embedding、数据库、oracle、timeout 或 retry。
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

## 可比性规则

- 只比较相同的 `contract_version`、selected contract hash、suite policy hash、execution protocol、oracle fixture 和 resolved runtime identity 的 M27 EvalRun。
- 修改 canonical Scenario、reference SQL、typed assertion、selector、gate、模型、检索、embedding、数据库 snapshot 或 reliability protocol 后，必须标记为新合同/新条件，不能把结果直接拼进同一基线序列。
- retrieval-only benchmark 继续独立记录；它不调用 PipelinePort，不能证明端到端 Text2SQL 收益。

### 人工复核的边界

M27 review bundle 是解释自动结果的旁路证据，不是第二套分数：它不改变 `eligible / observed / passed / failed / not_observed`、不改变 Gate，也不能与自动数字混算。Core / Stress 后复核全部自动失败、退款/SCD/金额/时间/递归等高风险合同，并抽样少量自动通过题。

自 `m27-review-bundle-v2` 起，bundle 保存 artifact 与各 checkpoint 的 SHA-256，复核前可验证来源仍是原文件。普通业务题没有 candidate SQL 时只能记为 `insufficient_evidence`；安全或预期拒绝题可以凭明确拦截证据判通过。人工分类只服务于错误聚合，绝不成为新分母或 Gate 输入。早期 v1 review 是无哈希的历史旁路材料，不能直接和 v2 的来源校验混用。

## 当前有效实验快照

这里保留仍能帮助判断当前路线的真实运行；它们未必已成为正式长期 baseline，也未必能作严格对照。每条都必须写清楚证据状态和解释边界。Smoke、运行事故、中断和外部服务异常不作为独立记录进入本账本。

| 类型 | 证据状态 | Run ID | 日期 | 协议 / resolved runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|---|
| Core | 过渡证据 | [`m27-core-20260809-qwen37plus-milvus-02`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-milvus-02.json) | 2026-08-09 | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off；19 logical / 19 physical | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-milvus-02.md)；required：28 passed / 0 failed / 6 not_observed；Gate `inconclusive` | 两个 QueryPlan timeout（商品 Top5、商品退款率排名）没有 candidate SQL，各贡献 3 条 external unavailable。该 run 早于 artifact 补齐 collection / embedding / corpus 字段：可用于解释 P0/P1 首轮结果，但不是严格 Milvus / P1 对照，也未登记长期 baseline。 |
| Stress | 当前单轮证据 | [`m27-stress-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-stress-20260809-qwen37plus-milvus-01.json) | 2026-08-10 | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`；195 docs / hash `8a8b6626...`；45s / retry0；SQLite seed；9 / 9 | [Markdown report](../../eval/reports/m27-stress-20260809-qwen37plus-milvus-01.md)；全部 assertion：7 passed / 14 failed / 4 not_observed；7 completed / 2 external unavailable；required：0 / 0 / 0，Gate `inconclusive` | Stress 全为 advisory，不是硬门。单次样本；失败集中在渠道 GMV、金额对账、递归类目、价格历史、渠道退款率与 schema context，不能据此断言 Milvus 因果或登记长期 baseline。 |
| Database Exception | 当前单轮证据 | [`m27-database-exception-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-database-exception-20260809-qwen37plus-milvus-01.json) | 2026-08-10 | 同上；7 / 7 | [Markdown report](../../eval/reports/m27-database-exception-20260809-qwen37plus-milvus-01.md)；全部 assertion：4 passed / 4 failed / 11 not_observed；3 completed / 4 external unavailable；required：0 / 0 / 0，Gate `inconclusive` | 该 selector 从 Stress 复用异常业务 Scenario，但 policy 独立，不能与 Stress 混算。单次样本；外部不可用较多，未登记长期 baseline。 |

后续当前合同下的 Core、Stress、Reliability、Database Exception 在本表追加一行，不与不同 selector / suite 混算。记录失去当前决策价值后移入文末「历史实验记录」，不按 M28、M29 等模块编号新增同级标题。

## 正式长期基线登记

只有用户明确指定某条 completed run 后，才在这里登记为正式长期基线：

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
