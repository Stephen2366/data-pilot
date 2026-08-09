# DataPilot Eval Baselines

> 本文从 `m27-v1` 开始记录**新的** EvalRun 基线与可比性规则。M26 及以前的 formal / challenge / diagnostic 账本已完整归档到 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)，**不与现在的数字直接比较**。

更新时间：2026-08-09

## 当前状态

- **当前合同**：`m27-v1`；每个业务问题是一个 canonical Scenario，多个 typed assertion 共享一次执行证据。
- **当前 catalog**：28 个 Scenario；分类为 Core / Stress / Manual Lab。Smoke、Reliability、Database Exception 是 selector，不是复制题面的独立题集。
- **当前真实 LLM 基线**：**尚未登记正式长期基线**。已完成 Smoke/Core 真实快照（见第 4、5 节），但有限次数的运行不代表完整模型通过率、成本或可靠性。
- **默认运行配置**：仍以 [runbook.md](runbook.md) 为准；M27 没有切换模型、检索、embedding、数据库、oracle、timeout 或 retry。

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

## 已运行的真实 LLM Smoke（非基线）

| Run ID | 日期 | Selector / Scenario | Resolved runtime | Oracle / artifact | Assertion views | Gate | 解释边界 |
|---|---|---|---|---|---|---|---|
| [`m27-smoke-20260809-02`](../../eval/reports/m27-artifacts/m27-smoke-20260809-02.json) | 2026-08-09 | `smoke`；4 logical Scenario / 4 physical attempts | Qwen `qwen3.7-plus`；inmemory deterministic / weighted；45s / retry0；LangFuse off | SQLite deterministic seed；[Markdown report](../../eval/reports/m27-smoke-20260809-02.md)；[Codex review](../../eval/reports/m27-reviews/m27-smoke-20260809-02-review.md) | required：passed 9 / failed 0 / not_observed 0；Codex review 4/4 pass | `passed` | 仅验证 API、Guard、Trace、artifact、report 闭环；不是 Core/Stress 基线，不能与 M26 `25/32` 等旧口径比较。 |
| [`m27-smoke-20260809-03`](../../eval/reports/m27-artifacts/m27-smoke-20260809-03.json) | 2026-08-09 | `smoke`；4 logical Scenario / 4 physical attempts | Qwen `qwen3.7-plus`；inmemory deterministic / weighted；45s / retry0；LangFuse off | SQLite deterministic seed；[Markdown report](../../eval/reports/m27-smoke-20260809-03.md)；[Codex review](../../eval/reports/m27-reviews/m27-smoke-20260809-03-review.md) | required：passed 9 / failed 0 / not_observed 0；Codex review 4/4 pass | `passed` | 与 `-02` 同条件的第二次 Smoke；只说明该小范围链路再次成功，不构成完整能力或可靠性基线。 |

首次 `m27-smoke-20260809-01` 在外部调用期间被工具时限中断，只留下 `running` checkpoint；M27 不支持 resume，该不完整 run 不进入 artifact、Gate 或分数账本。

## M27 已运行 Core 快照（未登记正式长期基线）

| Run ID | 日期 | Suite | Resolved runtime | Assertion views / Gate | 解释边界 |
|---|---|---|---|---|---|
| [`m27-core-20260809-qwen37plus-local-01`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-local-01.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-plus`；inmemory deterministic / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-local-01.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | 与下方 Milvus 组成一次配对；两侧的失败 assertion 完全相同。单次结果不与 M26 比较，也不推断稳定性。 |
| [`m27-core-20260809-qwen37plus-milvus-01`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37plus-milvus-01.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-plus`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37plus-milvus-01.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | 独立 clean collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`：195 docs、hash `8a8b6626...`。与 local 单次一致，只能说本轮未观察到结果变化。 |
| [`m27-core-20260809-qwen37max-local-05`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-local-05.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-max`；inmemory deterministic / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-local-05.md)；required：9 passed / 23 failed / 2 not_observed；Gate `failed` | **Qwen `account_arrearage` 污染**；不用于模型能力或检索比较。 |
| [`m27-core-20260809-qwen37max-milvus-01`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-milvus-01.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-max`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-milvus-01.md)；required：9 passed / 23 failed / 2 not_observed；Gate `failed` | **Qwen `account_arrearage` 污染**；不用于模型能力或检索比较。 |
| [`m27-core-20260809-qwen37max-local-06`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-local-06.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-max`；inmemory deterministic / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-local-06.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | 充值后连通性检查成功再运行；与下方 Milvus 当前快照一致，但样本仍不足以证明 max 与 plus 等价。 |
| [`m27-core-20260809-qwen37max-milvus-02`](../../eval/reports/m27-artifacts/m27-core-20260809-qwen37max-milvus-02.json) | 2026-08-09 | `core`；19 logical Scenario / 19 physical attempts | Qwen `qwen3.7-max`；Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim / weighted；45s / retry0；SQLite seed；LangFuse off | [Markdown report](../../eval/reports/m27-core-20260809-qwen37max-milvus-02.md)；required：29 passed / 5 failed / 0 not_observed；Gate `failed` | clean collection `datapilot_schema_docs_m27_qwen37max_qwenemb_20260809_183000`：195 docs、hash `8a8b6626...`。与 local 当前快照一致，不证明检索因果。 |

> **欠费污染与重复执行记录**：`m27-core-20260809-qwen37max-local-04/-05` 与 `...milvus-01` 的 `13/20/1`、`9/23/2`、`9/23/2` 均遇到 Qwen `account_arrearage`；正常业务题缺少 candidate SQL，却被当时 scorer 投影为 result/output failed，**不参与模型或 Milvus 比较**。`local-01/-02` 是前台超时后仍完成的重复 local 快照（28/6/0、29/5/0）；全部保留追溯，但不作为计划内重复实验。

## 首个真实基线登记模板

只有用户单独授权真实 LLM 运行后，才在此追加一条记录：

| Run ID | 日期 | Selector / Scenario | Protocol | Resolved runtime | Oracle / artifact | Assertion views | Gate | 解释边界 |
|---|---|---|---|---|---|---|---|---|
| *尚无* | — | — | — | — | — | — | — | 已有真实 Smoke/Core 快照，但尚未由用户指定哪条 completed run 作为正式长期基线。 |

每条记录至少链接脱敏 EvalRun JSON 与 Markdown report；只引用 `ResolvedRuntimeIdentity`，不以命令行表象替代实际模型、检索和 oracle 事实。
