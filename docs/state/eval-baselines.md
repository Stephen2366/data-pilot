# DataPilot Eval Baselines（M27 起）

> 本文从 `m27-v1` 开始记录**新的** EvalRun 基线与可比性规则。M13–M26 的 formal / challenge / diagnostic 账本已完整归档到 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)：它们是只读历史证据，**不能与 M27 数字直接比较**。

更新时间：2026-08-09

## 1. 当前状态

- **当前合同**：`m27-v1`；每个业务问题是一个 canonical Scenario，多个 typed assertion 共享一次执行证据。
- **当前 catalog**：28 个 Scenario；分类为 Core / Stress / Manual Lab。Smoke、Reliability、Database Exception 是 selector，不是复制题面的独立题集。
- **当前真实 LLM 基线**：**尚未建立**。已完成一次小范围真实 LLM Smoke（见第 4 节），但它只验证 Smoke 链路，不代表完整模型通过率、成本或可靠性。
- **默认运行配置**：仍以 [runbook.md](runbook.md) 为准；M27 没有切换模型、检索、embedding、数据库、oracle、timeout 或 retry。

## 2. M27 读数与分母

M27 不再使用一个混合的 `passed/32` diagnostic 总分。报告按 assertion kind 展示以下事实：

| 字段 | 含义 |
|---|---|
| `eligible` | 该 Scenario 声明了这种 assertion。 |
| `observed` | 有足够证据完成自动判断，即 `passed + failed`。 |
| `passed` / `failed` | 已观察到的自动断言结果。 |
| `not_observed` | 声明了 assertion，但因 pipeline error、external unavailable、缺 evidence 等原因不能自动判断。 |
| `unavailable` | `not_observed` 中 `external_unavailable` 的原因切片，不额外加入分母，也不等同 semantic wrong。 |

固定关系：`eligible = passed + failed + not_observed`，`observed = passed + failed`。自动能力率只在 observed 集合中计算：`passed / (passed + failed)`。

Gate 也是独立视图：selector / suite policy 决定 assertion 为 `required`、`advisory` 或 `excluded`，projector 再推导 `passed`、`failed` 或 `inconclusive`。Reliability 的多个 replicate 会归约为同一个逻辑 Scenario / assertion，不扩大业务问题分母。

## 3. 可比性规则

- 只比较相同的 `contract_version`、selected contract hash、suite policy hash、execution protocol、oracle fixture 和 resolved runtime identity 的 M27 EvalRun。
- 第一次真实 LLM M27 run 是新的事实锚点；不得把它与旧 formal / challenge / diagnostic 的 `10/10`、`26/32` 等数字作升降比较。
- 修改 canonical Scenario、reference SQL、typed assertion、selector、gate、模型、检索、embedding、数据库 snapshot 或 reliability protocol 后，必须标记为新合同/新条件，不能把结果直接拼进同一基线序列。
- retrieval-only benchmark 继续独立记录；它不调用 PipelinePort，不能证明端到端 Text2SQL 收益。

## 4. 已运行的真实 LLM Smoke（非基线）

| Run ID | 日期 | Selector / Scenario | Resolved runtime | Oracle / artifact | Assertion views | Gate | 解释边界 |
|---|---|---|---|---|---|---|---|
| [`m27-smoke-20260809-02`](../../eval/reports/m27-artifacts/m27-smoke-20260809-02.json) | 2026-08-09 | `smoke`；4 logical Scenario / 4 physical attempts | Qwen `qwen3.7-plus`；inmemory deterministic / weighted；45s / retry0；LangFuse off | SQLite deterministic seed；[Markdown report](../../eval/reports/m27-smoke-20260809-02.md)；[Codex review](../../eval/reports/m27-reviews/m27-smoke-20260809-02-review.md) | required：passed 9 / failed 0 / not_observed 0；Codex review 4/4 pass | `passed` | 仅验证 API、Guard、Trace、artifact、report 闭环；不是 Core/Stress 基线，不能与 M26 `25/32` 等旧口径比较。 |

首次 `m27-smoke-20260809-01` 在外部调用期间被工具时限中断，只留下 `running` checkpoint；M27 不支持 resume，该不完整 run 不进入 artifact、Gate 或分数账本。

## 5. 首个真实基线登记模板

只有用户单独授权真实 LLM 运行后，才在此追加一条记录：

| Run ID | 日期 | Selector / Scenario | Protocol | Resolved runtime | Oracle / artifact | Assertion views | Gate | 解释边界 |
|---|---|---|---|---|---|---|---|---|
| *尚无* | — | — | — | — | — | — | — | 未运行真实 LLM M27 基线。 |

每条记录至少链接脱敏 EvalRun JSON 与 Markdown report；只引用 `ResolvedRuntimeIdentity`，不以命令行表象替代实际模型、检索和 oracle 事实。

## 6. 历史账本

- 要查看 M13–M26 的模型、Milvus、embedding、formal / challenge / diagnostic、triage 与旧报告索引，请读 [eval-baselines-old.md](../archive-versions/eval-baselines-old.md)。
- 历史账本保留其原始口径和数字，便于追溯“当时为什么做这个决定”；它不再定义 M27 的命令、分母或 Gate。
