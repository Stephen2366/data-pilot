# DataPilot Eval 可观测与排障指南（v2）

> 本文说明 M27 Eval 跑完后，应该看什么、各类文件各自证明什么、遇到失败怎样定位。运行命令看 [runbook.md](state/runbook.md)，分母、Gate 和可比性规则看 [eval-baselines.md](state/eval-baselines.md)。旧 formal / challenge / diagnostic 的观测口径已经冻结，不适用本文。

## 先用一句话理解

M27 评测不是“每条 case 单独打一个总分”，而是：

```text
一个 Scenario 执行一次
        ↓
得到同一份执行证据（响应、trace、oracle 结果）
        ↓
多个 typed assertion 分别判断结果、上下文、计划、trace、安全等
        ↓
completed EvalRun artifact（长期事实）
        ↓
projector 生成 Gate 和 Markdown report（展示视图）
```

因此，排障时先问“执行发生了什么”，再问“哪一种 assertion 不通过”；不要只盯着一个总通过数。

## 1. 五类观测材料：谁是事实源，谁只是辅助

| 材料 | 默认位置 | 用途 | 能否改写自动结果 |
|---|---|---|---|
| **EvalRun artifact** | `eval/reports/m27-artifacts/<run-id>.json` | completed run 的长期、脱敏事实源 | 不适用；它就是自动事实 |
| **Markdown report** | `eval/reports/<name>.md` | 阅读 Gate、执行统计、assertion views | 否；它由 artifact 投影生成 |
| **checkpoint** | `.codex/temp_work/m27-checkpoints/<run-id>/` | 短期排障、人工复核所需的候选 SQL / 有限结果证据 | 否 |
| **JSONL trace** | `eval/traces/` | 单次请求的过程调试 | 否 |
| **review bundle** | `eval/reports/m27-reviews/` | Codex / 人工逐题业务复核 | 否；永远不改分母、Gate、CI |

最重要的顺序是：**artifact → report → checkpoint / trace → review**。

artifact 是长期保留的安全摘要，不保存完整 rows、完整 prompt、完整 response 或凭证；checkpoint 是短期材料，信息更完整但可能被清理。不要反过来把 Markdown 或人工 review 当作自动评分的事实源。

## 2. 一轮 Eval 的生命周期

```text
创建 run_id
  → 写 running manifest
  → 每个 Scenario / replicate：执行一次 pipeline，写一份 checkpoint
  → 全部完成：写 completed artifact，生成 Markdown report
```

`run_id` 是一次评测的唯一编号，绑定 manifest、checkpoint、artifact 和报告。

| run 状态 | 含义 | 能否进入 Gate / 基线 |
|---|---|---|
| `running` | 仍在执行；若遗留不结束，按 abandoned 处理 | 否 |
| `interrupted` / `failed` | 运行中断或整体失败，可能保留部分 checkpoint | 否 |
| `completed` | 已生成完整 EvalRun artifact | 可以被 projector 计算 Gate |

前台等待超时不代表 Eval 停止。先检查同一个 `run_id` 的 manifest、checkpoint 是否增长、artifact 是否已经生成；不要直接换一个 ID 重跑。具体执行纪律见 runbook。

## 3. 报告里的数字怎么读

M27 报告会同时给出 Gate、执行统计和 assertion views。它们回答的是不同问题。

| 字段 | 大白话解释 |
|---|---|
| `eligible` | 这个 Scenario 声明了该类检查。 |
| `passed` / `failed` | 有足够证据后，自动判断为通过 / 不通过。 |
| `not_observed` | 需要的证据没有拿到，不能自动判对错。 |
| `unavailable` | `not_observed` 中由外部不可用造成的切片；不是“模型答错”。 |
| `observed` | `passed + failed`，即真正完成判断的数量。 |
| `manual evidence` | 需要人工业务证据的数量，不是自动分数。 |

固定关系：

```text
eligible = passed + failed + not_observed
observed = passed + failed
自动能力率 = passed / observed
```

**Gate 不是能力率。** Gate 只消费当前 suite policy 中标为 `required` 的 assertion，输出 `passed`、`failed` 或 `inconclusive`。所以可能出现“某个 view 通过率不错，但 Core Gate 仍 failed”；也可能出现外部不可用导致 Gate `inconclusive`。

Reliability 的多次 replicate 也不会把同一个业务问题重复算进逻辑 Scenario 分母。

## 4. 先看哪里：一个实用排障顺序

1. **看 `run_status`**：不是 `completed`，先处理运行生命周期，不解读分数。
2. **看 Gate**：确认是哪个 suite、required 的 `passed / failed / not_observed` 分别是多少。
3. **看 Execution**：区分 logical completed、external unavailable、pipeline error、physical attempts。
4. **看 assertion views**：失败属于 `result_match`、`schema_context`、`query_plan`、`trace_complete`、安全还是输出合同？
5. **定位 Scenario**：需要 SQL、有限结果样本或详细 trace 时，再读该 run 的 checkpoint / JSONL。
6. **需要业务判断时才复核**：用 review bundle，不要用“人工感觉”覆盖自动事实。

一个常见误区是把所有 failed 都叫“模型不行”。M27 至少区分两层：

| 层次 | 例子 | 应该先做什么 |
|---|---|---|
| 执行层 | `external_unavailable`、`pipeline_error`、安全拒绝 | 看 execution status、error subtype、trace |
| 断言层 | SQL 结果错、指标映射错、Schema Context 缺失、输出列不符 | 看具体 assertion 的 reason 和结构化 trace 摘要 |

执行没有获得候选 SQL 的普通业务题，人工复核不能猜它“应该答对”；应保持 `insufficient_evidence`。

## 5. artifact、checkpoint 与 JSONL 各看什么

### EvalRun artifact：先看稳定、可比较的事实

artifact 包含：

- `contract_version`、`artifact_schema_version`；报告会额外标明其使用的 `projector_version`；
- catalog、selected contract、suite policy、run spec 的 hash；
- requested / resolved runtime identity；
- 每个 Scenario 的执行状态、脱敏 response/trace 摘要和 assertion 结果。

比较两个 run 前，要确认合同 hash、suite policy、执行协议、oracle fixture 和 resolved runtime identity 相同；否则只能并列记录，不能当作同一条基线的升降。

### checkpoint：看“这题到底发生了什么”

checkpoint 由每个已完成 Scenario / replicate 原子写入。它能提供短期的候选 SQL、reference SQL、有限行数结果预览与完整结构化证据，是人工 review 的材料来源。

它不是长期保证：清理后仍可阅读 artifact 和 report，但不能凭 artifact 重新构造完整 SQL 复核材料。

### JSONL trace：看请求过程

JSONL 用于看单次 `/api/query` 的执行步骤，例如 Schema Retrieval、QueryPlan、Plan Validation、SQL Generation、SQL Guard、SQL Execution。它尤其适合回答：

- 需要的表、字段、指标、Join 是否进入了上下文？
- QueryPlan 在哪一步被拦截？
- SQL Guard 是安全拒绝，还是 SQL 执行本身失败？

JSONL 是调试材料，不是 M27 的长期评分账本；不要用它重新拼旧 formal/challenge/diagnostic 分数。

## 6. 人工 / Codex review：只解释，不改判

review bundle 只能针对 completed run 生成，并会校验：

```text
artifact + 同 run checkpoint + canonical Scenario contract
```

每份材料记录 SHA-256。复核前可用 `--verify-bundle` 重新校验来源；checkpoint 被清理、替换或改写都会明确失败。

| 情况 | 合法的 review verdict |
|---|---|
| 有候选 SQL 的普通业务题 | `pass` / `fail` / `insufficient_evidence` |
| 没有候选 SQL 的普通业务题 | 只能 `insufficient_evidence` |
| 明确的安全拦截或预期拒绝 | 可依据拦截证据判 `pass` / `fail` / `insufficient_evidence` |

review 还会写结构化分类，例如 `business_sql_error`、`output_contract_error`、`schema_context_error`、`execution_evidence_unavailable`。这些标签帮助聚合问题，但**不参与自动 Gate 或 CI**。

## 7. LangFuse：可选观测旁路

当前默认是本地 artifact、Markdown 与 JSONL；LangFuse 默认关闭。

M27 只构造严格 allowlist 的 assertion payload：不上传完整 rows、SQL literal、prompt 或 provider 原始响应。实际上传仍需显式开启并得到授权，且不能影响本地 EvalRun、Gate 或报告生成。

因此排障优先级是：本地 artifact/report 正常 → 再看 JSONL → 只有确实需要 Cloud 可视化时才检查 LangFuse。不要把 LangFuse UI 或 Cloud 写入失败当作本地 M27 Eval 失败。

## 8. 常见问题速查

| 看到的现象 | 先检查 | 不要立刻得出的结论 |
|---|---|---|
| Gate `failed` | required assertion 的失败项 | “所有能力都退化了” |
| `not_observed` 增加 | execution status、error subtype、证据是否缺失 | “这些题都答错了” |
| local / Milvus 分数不同 | hash、runtime identity、collection 的 docs/dimension/hash | “Milvus 一定更好或更差” |
| report 与人工判断不同 | assertion reason、checkpoint、review policy | “人工能覆盖自动 Gate” |
| 前台命令超时 | 同 run 的 manifest / checkpoint / artifact | “这次 Eval 已停止，可以立刻重跑” |
| LangFuse 没有 trace | `LANGFUSE_ENABLED`、网络、上传授权 | “本地 Eval 一定失败了” |

## 进一步阅读

- 运行 selector、模型 / Milvus 开关和执行纪律：[runbook.md](state/runbook.md)
- 评测快照、分母、Gate、可比性：[eval-baselines.md](state/eval-baselines.md)
- 当前默认值与活跃坑：[AI_CONTEXT.md](state/AI_CONTEXT.md)
- Eval case / selector 的定义：[eval/cases/README.md](../eval/cases/README.md)
