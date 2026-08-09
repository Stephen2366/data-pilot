# M27 Diagnostic / Eval Case 体系优化计划

> 状态：方案已由用户确认，并已吸收 `m27-plan-review.md`、`m27-plan-review-v2.md` 中经复核采纳的建议；当前仅完成计划，不实施代码与 case 迁移。
>
> 本计划建立新的 `m27-v1` 评测合同。旧 formal / challenge / diagnostic 分数不兼容、不重算；既有 YAML、report、trace、triage、audit pack 继续作为只读历史证据保留。

## 1. 模块定位

M27 不以“再跑一轮 diagnostic”或“提高 `passed/32`”为目标，而是重建 DataPilot 的 EvalOps-lite 评测模型：

1. 一个业务问题只定义一次、只调用一次 pipeline；
2. Result、SchemaContext、QueryPlan、Trace、安全等多个 assertion 共享同一份执行证据；
3. Core / Stress 表达场景职责，Smoke / Reliability / Database Exception 表达选择或执行协议；
4. Diagnostic 改为报告视图，不再是额外调用 LLM 的题集；
5. manual、执行失败、外部不可用、自动断言和 gate policy 使用正交状态；
6. 每种 assertion 必须有真实 scorer，未知 assertion 在加载阶段直接失败；
7. 新运行先保存结构化结果，Markdown、LangFuse 和人工审计只是展示或外部 adapter。

通俗说，旧体系是“为了检查不同能力，把同一道题复印多份再分别答题”；新体系是“每道题只答一次，各科阅卷规则共同检查同一张答卷”。

## 2. 已复核的现状问题

### 2.1 重复问题仍会重复调用 LLM

- formal 10 条均能在 challenge 找到相同业务问题。
- formal 10 + challenge 16 + diagnostic extra 16 共 42 条 raw case，但仅对应 26 个 `semantic_group`。
- 单次 32 条 diagnostic 内部仍有 6 组重复业务问题：
  - `db_core_001` / `db_trace_001`：六月 GMV；
  - `db_multi_003` / `db_plan_001`：渠道 GMV；
  - `db_multi_004` / `db_prompt_001`：商品销售额 Top 5；
  - `db_multi_001` / `db_trace_002`：优惠券使用最多渠道；
  - `db_hard_003` / `db_prompt_002`：价格历史平均售价；
  - `db_join_002` / `db_prompt_003`：优惠券类型 GMV。
- `semantic_group_id` 当前只修正报告解释，`run_cases()` 仍逐 case 请求 `/api/query`。

### 2.2 部分 diagnostic check 只有名称，没有真实合同实现

当前以下 check 在基础安全、最终表列和 SQL 成功检查后落入默认 `ok`：

- `metric_mapping_match`
- `join_path_match`
- `plan_structure_match`
- `trace_steps_complete`

因此历史报告中的相应 `1.0 / ok` 不能证明指标映射、JoinPath、QueryPlan 或 Trace 合同真的通过。M27 必须先消除“未知 check 默认通过”的静默路径，再建立新基线。

### 2.3 能力视图仍使用整题 pass 代替 assertion 结果

- Capability Summary 按 case 标签聚合整题 pass/fail；Result 错误可能同时拉低 Schema Retrieval 和 QueryPlan。
- `plan_and_trace` 不是 Plan / Trace assertion 的真实分数，而是相关 case 的整体结果。
- `provider_reliability.passed_cases` 仍取整体 case pass；provider 正常返回但 SQL 语义错误，也会被表现为可靠性未通过。
- 同一 case 发生早期失败后，后续能力常被混写为 failed，而不是 `not_observed`。

### 2.4 manual / diagnostic / blocking / failed 仍存在交叉语义

- 最新报告中 runner `review_required=3`，但 `manual_or_diagnostic=5`，两套选择规则不一致。
- 成功执行的 manual case 会以 `passed=True` 进入总通过数，同时又进入 review 队列。
- 当前 `execution_failed = not passed and not review_required`，review 会压掉真实执行失败，两者不是真正正交。
- `phase3a_blocking` 是 case 固有属性，但同一场景在 Core、Stress、Reliability 中可能需要不同 gate 策略。

## 3. 已确认的总体决策

### 3.1 采用“唯一场景 + 多断言 + selector + diagnostic 视图”

M27 采用以下概念：

- **Scenario**：唯一业务问题、题面和权威业务合同。
- **Assertion**：针对同一次执行证据的一个可裁决检查。
- **Suite classification**：Core / Stress / Manual Lab，说明场景职责。
- **Selector**：Smoke / Reliability / Database Exception 等场景选择规则。
- **Execution protocol**：pipeline mode、重复次数、timeout/retry 候选等运行方式。
- **Report view**：Semantic、Context、Plan、Trace、Safety、Reliability、Manual 等统计投影。
- **Gate policy**：某 suite 下哪些 assertion 是 required / advisory / excluded。

### 3.2 Diagnostic 不再拥有独立题目

Diagnostic 是对同一轮 Core / Stress 运行的多维报告，不再通过 `--extra-cases` 追加同题的新 LLM 调用。

### 3.3 旧合同只读冻结

- `m26-v1` 及更早的 YAML、报告与数字不由新 scorer 重算。
- 不搬动会导致历史路径失效的旧产物。
- 新 runner 不承诺加载旧单-check YAML。
- M26 audit 的 legacy Markdown adapter 只服务冻结历史输入；不得成为新运行的数据来源。
- 如新数据结构会影响旧 audit 代码，提取最小只读 legacy adapter，而不是把兼容字段扩散进新 Interface。

### 3.4 不建设完整 Eval 平台

M27 保存结构化 run / assertion 结果，但不新增持久化数据库表、多人标注平台、任务队列或完整实验管理系统；平台化能力留给独立 `eval-bench`。

## 4. 目标架构与核心 seam

### 4.1 对外 Interface

推荐让调用方只依赖一个高杠杆入口，并把同轮运行资源交给一个有唯一生命周期所有者的环境 factory：

```python
evaluator = Evaluator(
    environment_factory=run_environment_factory,
    checkpoint_store=checkpoint_store,
)

run = evaluator.evaluate(run_spec)
```

其中：

- `EvalRunSpec` 冻结 selected contract、replicate policy、execution protocol、gate policy 和 requested runtime constraints；
- `RunEnvironmentFactory` 为一轮运行创建一个 `RunEnvironment`，并负责 seed/counterfactual、FastAPI 依赖注入、oracle snapshot、vector index 和 cleanup；
- `RunEnvironment` 同时提供 typed `PipelinePort`、`OraclePort`、snapshot identity 与 resolved runtime identity，保证两个 adapter 不会各自创建 seed；
- `PipelinePort` 的生产 adapter 使用 FastAPI/TestClient，测试 adapter 使用内存 fake；
- `CheckpointStore` 负责 run manifest、逐 Scenario checkpoint 和最终 artifact 原子落盘；
- `Evaluator` 持有 `RunEnvironment` 的整轮生命周期；环境初始化失败属于 run-level setup failure，不产生场景级语义失败；
- 这些 Interface 必须字段固定、职责明确，不能演化成任意对象都能塞入的 service locator。

调用方不需要手工编排 catalog、HTTP 调用、trace 读取、reference SQL、scorer 顺序、checkpoint 和分母计算。复杂度集中在 `Evaluator` module 的实现内部，测试也优先通过同一 Interface 验证。

一次执行的核心不变量：

```text
每个 (run_id, scenario_id, replicate_id) 最多调用一次 PipelinePort
```

Reliability 可以为同一 Scenario 建立多个 replicate，但同一 replicate 下所有 assertions 必须共享同一份证据。

### 4.2 内部数据流

```text
EvalRunSpec + Scenario Catalog
              │
              ▼
       唯一 Scenario 列表
              │
              ▼
RunEnvironment（Evaluator 持有整轮生命周期）
├── resolved runtime identity
├── Run / Oracle Snapshot（每轮只创建一次）
├── PipelinePort：执行候选请求
├── OraclePort：执行 reference SQL
└── cleanup
              │
              ▼
       Evidence Builder
              │
              ▼
       ExecutionEvidence
              │
              ├── Result Assertion
              ├── Schema Context Assertion
              ├── QueryPlan / Join Assertion
              ├── Trace Assertion
              ├── Safety / Expected-Rejection Assertion
              └── Output Contract Assertion
              │
              ▼
       AssertionResult[]
              │
              ├── 每 Scenario 增量 checkpoint
              └── 最终 EvalRun artifact 原子落盘
              │
              ├── Versioned Report Projector → Markdown
              ├── LangFuse adapter
              └── 未来 Human Audit evidence adapter（M27 不实现新审查流程）
```

Candidate SQL 和 reference SQL 必须使用同一个 seed / counterfactual / snapshot。当前 scorer 内重新创建 SQLite seed 的实现不进入新体系；reference 执行属于 Evidence Builder，而不是纯 scorer。

### 4.3 建议的数据结构

#### ScenarioContract

至少包含：

- `scenario_id`
- `question`
- `user_role`
- `business_description / authority_refs`
- `assertions[]`
- `tags[]`
- `classification`

Scenario 顶层只保留所有 scorer 都需要理解的身份和业务语义，不放置大量 scorer 专属可选字段。`reference_sql`、columns、alternatives、expected plan 等由 typed assertion 自己拥有；共享指标口径通过 `domain_pack/metrics.yaml` 等权威定义的稳定引用解析。

#### Typed AssertionContract

至少包含：

- `assertion_id`
- `kind`
- 当前 kind 所需的专属合同字段
- `authority_refs`（如引用 metric contract）

不同 kind 应解析成不同的内部类型，而不是所有 scorer 读取同一个大字典。若 result 和 output assertion 需要共享列契约，应通过一个明确的 typed oracle/output spec 引用，不能各复制一份后独立漂移。

#### EvalRunSpec

至少包含：

- run identity；
- selected contract / suite policy identity；
- selected scenario ids；
- replicate policy；
- execution protocol；
- gate policy；
- oracle snapshot / fixture identity；
- requested runtime constraints。

CLI/CI 对 `inconclusive` 的退出策略不属于 EvalRunSpec。Projector 只产出 gate fact，CLI adapter 再用独立 `ExitPolicy` 映射退出码。

#### RunEnvironment / ResolvedRuntimeIdentity

`RunEnvironment` 是有实际深度的运行期 module，不是 ports 的转发容器。它至少负责：

- 一次性创建并清理 seed / counterfactual / snapshot；
- 把同一 engine/fixture 注入 PipelinePort 与 OraclePort；
- 初始化并验证本轮 vector index；
- 冻结 requested 与 resolved runtime identity；
- 在第一条 Scenario 执行前报告 environment setup failure。

`ResolvedRuntimeIdentity` 至少记录实际 provider/model、pipeline mode、retrieval backend/fusion、embedding provider/model/dimension、Milvus collection/row count/schema docs hash、oracle fixture/hash，以及 timeout/retry 实际值。显式 requested constraint 与 resolved 值冲突时必须 fail fast；未显式指定而由默认值解析的配置可以继续，但必须保存 resolved 值。

#### ExecutionEvidence

至少包含：

- run / scenario / replicate identity；
- pipeline mode、model、retrieval、oracle 和 contract version；
- logical call 与 physical attempts；
- HTTP / provider / transport 状态；
- neutral execution status；
- 候选 response 的必要结构化字段；
- SchemaGraph、QueryPlan、candidate SQL；
- Guard / Fidelity / execution / output contract 证据；
- reference SQL 的 expected result / normalized diff evidence；
- latency / token / cost 等可用运行信息。

`ExecutionEvidence` 是 scorer 消费的运行时结构，不等于长期 artifact 必须嵌入完整 raw response / trace。长期保存遵守第 11 节的脱敏和 evidence-ref 策略。

#### AssertionResult

至少包含：

- `assertion_id / kind`
- `status`
- `reason`
- `issue_tags`
- `evidence_refs`
- `metadata`

`AssertionResult` 只表达观察事实，不包含 `required/advisory/excluded` 等 suite policy，也不直接覆盖 Scenario 的执行状态或把 manual pending 编造成数值 pass。

#### EvalRun

至少包含：

- run identity、requested configuration 与 resolved runtime identity；
- `run_status = running / completed / interrupted / failed`；
- contract / artifact schema version；projected view / report 另记录 projector version；
- catalog / selected contract / suite policy / run spec hash identity；
- `ScenarioRun[]`；
- ExecutionEvidence 的长期安全表示；
- AssertionResult[]。

EvalRun 不保存可以从明细推导的 report counts 或 capability summaries，防止结构化明细和汇总再次成为两份事实源。Gate result 和所有报告统计由 versioned projector 从 EvalRun 推导；如未来因性能缓存汇总，必须携带 projector version，并能通过测试从明细重算一致。

## 5. Scenario 合同草案

示意结构：

```yaml
contract_version: m27-v1

scenarios:
  - id: june_channel_gmv
    question: 2026 年 6 月各渠道 GMV 排名，按 GMV 降序、渠道名称升序排列
    user_role: ops
    classification: stress
    tags: [channel_analysis, gmv, multi_table]
    business:
      metric_refs: [gmv]
      authority_refs: [domain_pack/metrics.yaml]
    assertions:
      - id: semantic_result
        kind: result_match
        oracle:
          reference_sql: |
            SELECT ...
          columns: [channel_name, gmv]
          tolerance: 0.01
      - id: schema_context
        kind: schema_context
        alternatives:
          - tables: [channels, orders]
            required_columns: [channel_name, order_amount, paid_at, channel_id]
      - id: query_plan
        kind: query_plan
        expected:
          tables: [channels, orders]
          metrics: [gmv]
      - id: trace_complete
        kind: trace_complete
        required_steps: [schema_retrieval, schema_context, query_plan, sql_generation, sql_guard, sql_execution]
```

具体 YAML 字段在实施前通过 fixture 验证可读性。typed assertion 的 Interface 只暴露调用者理解该合同所需的信息；解析、依赖检查、trace 定位和比较算法藏在 scorer 实现内部。

## 6. Assertion / Scorer 架构

### 6.1 严格注册

建立 `assertion.kind -> scorer` 注册表，并满足：

- catalog 加载时验证所有 kind；
- 未注册 kind 立即报错；
- 禁止默认 `passed=True / ok`；
- 每个 scorer 明确声明所需 evidence；
- scorer 是纯比较逻辑，不在内部重新调用 LLM、重新读全局 trace、执行 reference SQL、创建 seed 或访问隐式外部状态。

### 6.2 Evidence Builder 与 OraclePort

Result oracle 的职责明确放在 scorer 之前：

```text
一次 Run Snapshot
├── PipelinePort 执行候选查询
├── OraclePort 在同一 snapshot 执行 reference SQL
└── Evidence Builder 产出 candidate result + expected result + normalized evidence
        ↓
纯 result scorer 比较 evidence
```

要求：

- candidate 与 reference 共享同一 SQLite engine/session snapshot 或等价的只读数据库快照；
- counterfactual fixture 只创建一次，并同时注入 PipelinePort 与 OraclePort；
- reference SQL 执行失败属于 oracle/eval contract error，不得伪装成模型语义失败；
- assertion scorer 不得为每条 result case 重新 seed 数据库。

### 6.3 基础执行事实与业务 assertion 分离

以下属于每次运行自动采集的 lifecycle evidence，不要求 Scenario 重复声明：

- HTTP / route；
- provider availability；
- attempt / timeout / retry；
- SQL 是否生成、Guard、执行状态；
- latency / cost。

以下属于 Scenario 显式 assertions：

- `result_match / expected_value`
- `output_contract`
- `schema_context`
- `query_plan`
- `join_path`
- `trace_complete`
- `safety_block`
- `expected_rejection`
- 必要时的人工 rubric

### 6.4 不使用早返回掩盖证据

- 上游失败导致证据不存在时，下游 assertion 返回 `not_observed`。
- 已经存在的 Context / Plan / SQL / Result 证据应尽量全部评分。
- scorer 不把“未执行”记为能力失败，也不把“当前不适用”记为通过。
- suite gate 可以因 required assertion 未观察而成为 `inconclusive`，但 semantic view 仍保持 `not_observed`。

### 6.5 当前占位 check 的处置

M27 不直接照搬旧名字，先确认它们真正要回答的问题：

- `metric_mapping_match`：检查 SchemaGraph / QueryPlan 的指标绑定，还是最终 SQL 结果；
- `join_path_match`：检查 QueryPlan JoinPath、candidate SQL AST，或两者一致性；
- `plan_structure_match`：明确 tables / joins / metrics / filters / group / order 的匹配层级；
- `trace_steps_complete`：检查步骤存在、状态、顺序和 allow-skipped 规则。

每项先有正反 fixture 和失败 reason，再允许进入正式 assertion registry。

## 7. 正交状态模型

### 7.1 Execution Status

建议枚举：

- `completed`
- `rejected`
- `pipeline_error`
- `external_unavailable`

Execution Status 只记录实际发生了什么。`rejected` 是否符合预期、拒绝原因是否正确，统一由 expected-rejection / safety assertion 判断。

### 7.2 Assertion Status

建议枚举：

- `passed`
- `failed`
- `not_observed`

`not_observed` 必须携带稳定 reason，例如：

- `external_unavailable`
- `pipeline_error`
- `missing_evidence`
- `oracle_error`
- `manual_evidence_required`

没有声明某 assertion 的 Scenario 是 `ineligible`，不创建 `not_applicable` AssertionResult。`not_applicable` 如需展示，只能是跨场景 projector 的视图概念。

### 7.3 Manual Evidence 边界

M27 不建立持久化 `ReviewStatus`、人工 verdict 或 review queue。Manual Lab 中需要人工判断的 assertion 输出 `not_observed(reason=manual_evidence_required)` 和脱敏 evidence bundle；未来若建设人工审查系统，再由独立 adapter 管理其工作流状态，不能反向污染本轮 AssertionResult。

### 7.4 Gate Policy / Gate Result

Gate policy：

- `required`
- `advisory`
- `excluded`

Suite gate result：

- `passed`
- `failed`
- `inconclusive`

外部不可用或 required assertion 未观察时，suite 可以 `inconclusive`；CLI/CI adapter 是否 fail-closed 由独立 `ExitPolicy` 决定，不写入 EvalRunSpec，也不把它改写为 semantic wrong。

Gate Policy 只存在于 EvalRunSpec / suite policy 中，不能写进 AssertionResult。这样同一个 assertion 可以在 Core 中 required、在 Stress 中 advisory、在 Reliability 中 excluded。

## 8. Suite、Selector 与执行协议

### 8.1 Core

- 生产主链路必须稳定的自动场景；
- 业务合同明确；
- 有 deterministic result、安全或 expected-rejection oracle；
- required assertions 参与主回归 gate。

### 8.2 Stress

- 递归类目、SCD、退款归因、复杂 Join、数据异常和多表放大；
- 尽量自动裁决；
- 默认以 advisory 或独立 stress gate 展示，不与 Core 共用一个阈值。

### 8.3 Manual Lab

仅保留：

- 业务口径确实未确定；
- 尚无可信 oracle / rubric；
- 用于探索未来能力且不应进入自动分母。

“合同已明确但 scorer 未实现”标为 `automation_backlog`，不算 manual pass。

### 8.4 Smoke Selector

- 从 canonical scenarios 选择少量便宜、稳定的场景；
- 使用明确的轻量 protocol；
- 验证 API、Trace、Guard、SQL execution 和报告链路；
- 不复制弱化题面，也不代表完整模型能力。

### 8.5 Reliability Selector / Protocol

- 复用 canonical scenario；
- protocol 声明重复次数、timeout/retry 候选和固定条件；
- 同一场景的 replicate 不增加 independent scenario count；
- 分别报告 logical executions 和 physical attempts。

### 8.6 Database Exception Selector

继续沿用当前“引用既有 case、不复制正文”的正确方向，但新体系直接选择 canonical scenario id。

### 8.7 Diagnostic View

Diagnostic 读取一轮 EvalRun，输出 Semantic、Context、Plan、Trace、Safety、Output、Reliability、Manual 等视图，不再次执行 Scenario。

## 9. 分母合同

每个 report view 至少同时报告：

- `eligible`：声明了该 assertion；
- `observed`：证据足以自动评分；
- `passed`：observed 中通过；
- `failed`：observed 中失败；
- `not_observed`：已声明 assertion，但证据不足；
- `unavailable`：`not_observed_reason=external_unavailable` 的派生切片，不是独立 AssertionStatus；
- `manual_evidence_required`：`not_observed_reason=manual_evidence_required` 的派生切片，表示需要人工证据判断，不表示已创建审查任务。

固定数学关系：

```text
eligible = passed + failed + not_observed
observed = passed + failed
unavailable <= not_observed
```

未声明该 assertion 的 Scenario 为 `ineligible`，不进入 eligible，也不生成一条假的 `not_applicable` 结果。

自动能力率只计算：

```text
passed / (passed + failed)
```

同时必须并列展示：

- end-to-end scenario outcome；
- provider availability；
- required assertion gate；
- not_observed / unavailable 数量和原因。

禁止：

- 把 unavailable 从 end-to-end 报告中删除；
- 把 unavailable 计为 semantic wrong；
- 把 manual evidence required 计为 passed；
- 把多个 assertion 相加成一个 diagnostic 总分；
- 把 raw assertion 数解释成独立自然语言问题数。

Reliability 额外报告：

- logical execution success / total；
- first-attempt success；
- final success；
- physical attempt count；
- timeout / retry / latency / cost 分布。

## 10. 当前 case 的候选迁移方向

下列方向已经确认进入迁移审计，但逐题最终合同仍需在实施前形成 migration matrix 并过用户确认门：

| 当前 case / semantic group | 候选去向 | 说明 |
|---|---|---|
| formal 与 challenge 的 10 组重复题 | 合并为唯一 Core / Stress Scenario | formal / challenge 仅作为历史 suite 名保留 |
| `db_core_001` + `db_trace_001` | 单一六月 GMV Scenario | Result + Trace 共用证据 |
| `db_multi_003` + `db_plan_001` | 单一渠道 GMV Scenario | Result + QueryPlan + Join assertions |
| `db_multi_004` + `db_prompt_001` | 单一商品 Top 5 Scenario | Result + SchemaContext assertions |
| `db_multi_001` + `db_trace_002` | 单一优惠券渠道 Scenario | Result + Trace assertions |
| `db_hard_003` + `db_prompt_002` | 单一 SCD 平均售价 Stress Scenario | 自动化前补边界反事实 |
| `db_join_002` + `db_prompt_003` | 单一优惠券类型 GMV Scenario | Join + Context + Result assertions |
| `db_hard_001` | Stress 自动结果题 | `item_gmv` 与 root label 合同已明确 |
| `db_join_003` | 合并进商品退款率 Scenario | 与 `db_core_002` 共享结果、归因和 Join 合同 |
| `db_plan_003` | 自动 expected-rejection | 删除与 `manual_review` 的冲突语义 |
| `db_plan_004` | 自动 expected-rejection | 当前不支持 multi-step 是明确产品能力边界 |
| `db_prompt_002` | 不再独立执行 | 合并进 SCD Scenario |
| exception 新增 3 题 | 独立 Stress Scenario | 由 exception selector 选择 |
| smoke 重复题 | 复用 canonical Scenario | 不保留弱 `contains` 复制题 |

真正进入 Manual Lab 的题必须逐条写明“尚未决定的业务问题”或“缺失的裁决依据”。

## 11. 历史兼容与产物策略

### 11.1 新旧合同隔离

- 新合同版本：`m27-v1`。
- 旧 `m26-v1` 和更早报告不与新结果直接比较。
- 新报告明确写出四类 hash、三个独立 version、selector、protocol、oracle，以及 requested / resolved runtime identity。

Hash 拆成四个用途不同的指纹：

- `catalog_hash`：全部 canonical Scenario + typed assertions 的规范化内容，用于标识完整 catalog；
- `selected_contract_hash`：本轮实际选中的 Scenario + typed assertions + reference SQL + 已解析的 metric contract 内容；
- `suite_policy_hash`：相关 selector、resolved selected scenario ids、classification 和 gate policy；
- `run_spec_hash`：selected contract / suite policy hash + replicate policy + execution protocol + oracle fixture identity + requested runtime constraints。

完整 catalog 中未被本轮选择的 Scenario 发生变化时，`catalog_hash` 可以变化，但不应单独改变该轮 `selected_contract_hash` 或 `run_spec_hash`。

规范化规则：

- 忽略 YAML 注释、文件路径、mapping key 顺序、换行风格和纯排版；
- Scenario / assertion 集合按稳定 id 规范化，只有明确有语义的列表顺序才保留，例如 trace required steps；
- reference SQL 统一换行与无意义首尾空白，但不采用可能改变 dialect/语义的通用 AST 重写；
- metric reference 必须把解析后的权威合同内容纳入 hash，不能只 hash metric 名称；
- 仅调整 YAML 排版不产生新 hash，真实题面、oracle、assertion 或 policy 变化必须可观察。

版本拆成三个独立维度：

- `contract_version`：Scenario / Assertion 业务合同版本；
- `artifact_schema_version`：EvalRun JSON 持久化结构版本；
- `projector_version`：分母、gate 和报告视图推导算法版本。

Projector 必须拒绝不支持的 artifact schema version，不能猜测未知字段含义。

### 11.2 Requested / Resolved Runtime 对账

- run manifest 先保存 requested configuration；
- `RunEnvironment` 初始化后冻结 `ResolvedRuntimeIdentity`，并在第一条 Scenario 前完成对账；
- 显式 constraint 不一致、oracle fixture/hash 不一致、Milvus collection/schema docs hash/dimension 等运行事实不合法时，run 以 `failed(reason=environment_setup_failed)` 结束；
- 未显式指定的默认值只记录 resolved 值，不误报 mismatch；
- 后续 projector、报告和基线比较使用 resolved identity，不用“命令看起来相同”替代事实核验。

### 11.3 旧文件处理

- 不移动、删除、覆盖旧 YAML 和历史报告。
- 在说明文档标记 legacy / read-only，避免继续作为新入口。
- 新 run 不写入旧报告文件名。
- 不为兼容旧报告继续保留混乱的 `EvalCase.check_type` Interface。

### 11.4 结构化事实源

- 新运行逐 Scenario 写 checkpoint，完成后原子生成最终 JSON artifact，再从 JSON 渲染 Markdown。
- Markdown 不反向参与新评分或汇总。
- LangFuse 回写只消费 AssertionResult，不自行重算。
- EvalRun 只保存原始 ScenarioRun / ExecutionEvidence / AssertionResult，不保存可推导 report counts。
- Versioned projector 从 EvalRun 推导 gate 和各 report views；Markdown 与 LangFuse adapter 均消费 projector/AssertionResult，不建立第二份统计事实源。

### 11.5 长运行、partial evidence 与原子落盘

- 执行前先原子创建 `run_status=running` 的 manifest，写入 run identity、requested configuration、版本和 hash；
- 持久化 run lifecycle 为 `running / completed / interrupted / failed`；
- 每个 `(run_id, scenario_id, replicate_id)` 完成后立即追加结构化 checkpoint；
- 可捕获的外层超时、人工中断或 setup failure 写为 `interrupted` / `failed`，保留已完成/未完成 identity；
- 进程被直接杀死时允许遗留 `running` manifest；读取方把无有效运行所有者的旧 `running` 视为 `abandoned/incomplete`，不得送入 projector 或 gate；
- 所有非 `completed` artifact 都不能被报告成完整 EvalRun；
- 最终 artifact 先写临时文件、校验完整性后原子替换目标文件；
- Resume 不是 M27A 硬门，但 checkpoint 格式要为未来 resume 保留稳定 identity 和幂等条件；
- Resume 未实现前，已存在的 `run_id` 一律拒绝再次启动；重跑必须生成新 run id，不覆盖旧 manifest/checkpoint；
- 一次性 checkpoint 写入 `.agent_work/temp/`，长期完整 EvalRun JSON 进入 `eval/reports/`；以共享临时目录作为唯一默认路径。

### 11.6 长期 artifact 脱敏与证据保留策略

实施前必须确定 allowlist，不能把完整 response/trace/rows 默认塞进长期 EvalRun：

- raw JSONL trace 继续保存在 gitignored `eval/traces/`，只作为可清理的短期调试证据，不作为长期复核的唯一依赖；
- 长期 EvalRun 内保存自足的安全 evidence bundle：脱敏 candidate/reference SQL、结果 schema、row count、normalized hash、结构化 diff、有界脱敏反例、trace step 摘要和 issue tags；
- 外部 evidence ref 可继续保存 `evidence_ref + sha256`，但 raw 文件被清理后不能只靠该引用宣称可重新审查；
- 默认不长期保存全量结果 rows；邮箱、手机号及安全策略保护字段必须删除或替换为 `[redacted]`；
- candidate/reference SQL 可以保存，但需对可能包含敏感 literal 的位置执行稳定脱敏；
- 安全阻断题不得因为评测 artifact 绕过 Guard 泄露敏感结果；
- provider metadata 使用 allowlist，不保存 API key、authorization header 或完整敏感 prompt；
- LangFuse adapter 使用比本地 artifact 更严格的上传白名单，不默认上传 rows、完整 prompt 或敏感 SQL literal；
- projector 和 Markdown 只能消费已脱敏长期表示，不能为了展示再读取并嵌入 raw 敏感内容。

长期证据承诺限定为：足以重算自动 scorer，并支持针对 SQL 与结构化差异的人工复核；不承诺恢复完整 raw rows 或 provider response。

### 11.7 人工审查范围

- M27 只为未来人工审查保存足够、脱敏、可追溯的安全 evidence bundle；
- 旧 M26 audit 继续走 legacy adapter；
- M27 不重新设计人工 verdict、二审、mutation 审查或多人工作流；
- Human audit adapter 仅作为未来扩展点，不进入 M27A/M27B 核心交付和验收分母。

## 12. 候选代码落点

最终命名可在实施时按 locality 微调，但应保持一个主要外部 Interface，避免过多浅层文件：

```text
eval/
  contracts.py          # Scenario / Evidence / AssertionResult / EvalRun 稳定结构
  evaluator.py          # Evaluator.evaluate(run_spec) 深 module
  environment.py        # RunEnvironment 生命周期、snapshot 与 resolved runtime 对账
  ports.py              # PipelinePort / OraclePort / CheckpointStore typed seam
  catalog.py            # 新合同加载、selector 和严格验证
  evidence.py           # 同一 snapshot 的候选/reference evidence 构建与脱敏
  assertions/           # 内部纯 scorer 与 registry
  projectors.py         # 从 EvalRun 推导 gate / report views 的版本化 projector
  reporting.py          # JSON finalize 与 Markdown / LangFuse adapters
  legacy.py             # 仅冻结历史需要的最小只读 adapter（如确有需要）
  run_eval.py           # CLI adapter，最终切到 Evaluator.evaluate()

eval/cases/catalog/
  scenarios.yaml
  suites/
    core.yaml
    stress.yaml
    manual-lab.yaml
  selectors/
    smoke.yaml
    reliability.yaml
    database-exception.yaml
```

`catalog/` 是后续 canonical Scenario 与 suite 选择规则的长期权威目录，不绑定 M27 模块编号；`m27-v1` 只保留为本次新合同版本。旧 formal / challenge / diagnostic YAML 保持原路径并标记为 legacy/read-only，本轮不为整理目录而搬动它们。

如果实际实现发现上述拆分产生只转发参数的浅层 module，应合并回 `evaluator.py` 或 `catalog.py`，以 Interface 深度和 locality 为准，不以目录整齐为目标。

## 13. 实施阶段

M27 仍是一个模块，但设置两个可独立验收的内部里程碑，避免所有 P0-P7 完成后才第一次整体验收：

- **M27A：可信执行地基**——migration matrix、typed contract、严格 loader、一次执行、共享 oracle snapshot、真实 scorer、增量 checkpoint 和安全结构化 artifact；
- **M27B：消费与切换**——suite/selector/gate、versioned projector、Markdown/LangFuse、legacy 隔离、旧入口退场和正式切换。

### M27A：可信执行地基

#### P0：冻结范围与建立迁移账本

##### P0-1 全量 case inventory

- 盘点 smoke、formal、challenge、diagnostic extra、exception、reliability 的所有 case；
- 建立 `old_case_id -> scenario_id -> assertions -> classification -> selectors` 矩阵；
- 识别精确重复、题面近似但合同不同、真正独立问题；
- 核对 reference SQL、指标、时间、过滤、排序、LIMIT、alias 和人工 rubric；
- 单列当前无真实 scorer 的 check。

##### P0-2 用户确认门 A：逐题合同迁移

在修改正式 case 前向用户提交：

- canonical scenario 清单；
- 合并/保留/淘汰理由；
- Core / Stress / Manual Lab 去向；
- 每个 Scenario 的 assertions；
- 存在业务歧义或 oracle 风险的题。

用户确认前不改正式题面、reference、分母或 scorer。

#### P1：Typed Contract、严格加载器与 Hash

- 定义小顶层 ScenarioContract、typed AssertionContract、EvalRunSpec、ExecutionProtocol 和 Selector；
- 实现 `catalog_hash / selected_contract_hash / suite_policy_hash / run_spec_hash`；
- 独立定义 `contract_version / artifact_schema_version / projector_version`；
- assertion kind 严格注册，未知 kind 加载失败；
- 检查 duplicate scenario id、duplicate assertion id、悬空 selector、缺 reference、冲突分类；
- 用最小 fixture 验证 schema 易读性、规范化 hash 和错误信息。

#### P2：RunEnvironment、一次执行、共享 Snapshot 与增量 Checkpoint

- 实现 `Evaluator.evaluate(run_spec)`、RunEnvironmentFactory、PipelinePort、OraclePort、CheckpointStore；
- `Evaluator` 每轮只打开一次 RunEnvironment，由其创建 oracle/counterfactual snapshot 并同时提供给 candidate 和 reference 路径；
- 初始化并冻结 ResolvedRuntimeIdentity，显式 requested/resolved mismatch 在首个 Scenario 前 fail fast；
- 实现每个 `(run_id, scenario_id, replicate_id)` 最多一次 logical pipeline 调用；
- 记录 replicate id 与 physical attempts；
- Evidence Builder 从同一次 response / JSONL trace 与 reference result 构造 ExecutionEvidence；
- 不允许 scorer 重新调用 pipeline、执行 reference SQL 或创建 seed；
- 执行前原子写 `running` manifest，每个 Scenario 完成后写幂等 checkpoint，最终 artifact 原子落盘；
- 捕获异常写 `interrupted/failed`；硬崩溃遗留 `running` 按 incomplete/abandoned 处理；
- Resume 未实现前拒绝复用已有 run id；
- fake adapter 测试多个 assertions 只触发一次 PipelinePort；
- `rejected`、external timeout、pipeline error、Guard block、SQL execution error 分别形成中性 execution status 和证据。

#### P3a：代表场景垂直切片

- P0 逐题合同确认后，选择一条已确认代表场景或等价确定性 fixture；
- 一次打通 typed Scenario → RunEnvironment → 一次 PipelinePort → 同 snapshot oracle → Result + Context + Plan + Trace → checkpoint → EvalRun；
- 垂直切片至少覆盖一个 `not_observed` 路径、resolved runtime 对账和长期安全 evidence bundle；
- 先通过 `Evaluator.evaluate(run_spec) -> EvalRun` 检查 Interface 与 artifact 形状，再批量迁移；
- 不因垂直切片跳过全量 migration matrix，也不在用户确认前改写正式 case。

#### P3b：Assertion Registry、全部真实 scorer 与安全 Artifact

- 迁移 result / expected value / output / safety / expected-rejection；
- 迁移已可信的 SchemaContext alternatives 和 plan-validation scorer；
- 为 metric mapping、JoinPath、QueryPlan structure、Trace completeness 建立真实正反 scorer；
- 每个 scorer 明确 evidence dependency；
- 上游证据缺失返回 `not_observed`；
- manual rubric 不产生自动 numeric pass；
- AssertionResult 不携带 gate policy；
- EvalRun 只保存原始明细，不保存派生汇总；
- 落实自足安全 evidence bundle、SQL literal 脱敏和 LangFuse allowlist；
- raw trace 仅作短期调试证据，长期自动重算与 SQL 复核不依赖其永久存在；
- 非 completed run 保留 partial evidence，但不能进入 projector/gate。

#### M27A 内部验收门

- migration matrix 已确认；
- typed contract、四类 hash 与三个独立 version 稳定；
- 一个 replicate 内多 assertions 只调用一次 PipelinePort；
- RunEnvironment 唯一持有并清理 snapshot，candidate/reference 使用同一实例；
- requested/resolved runtime identity 对账通过；
- 所有正式 assertion 都有真实 scorer 和正反例；
- running/failed/interrupted/abandoned 语义、run id 防覆盖、原子 finalize 通过测试；
- 长期安全 evidence bundle 在 raw trace 缺失时仍足以重算自动 scorer；
- 新测试主要通过 `Evaluator.evaluate(run_spec) -> EvalRun` 验证，不依赖内部函数调用顺序。

M27A 通过后再进入 selector/gate/report 和正式入口切换，避免在核心数据结构未稳定时扩展 adapter。

### M27B：消费、报告与正式切换

#### P4：Suite / Selector / Gate Projector

- 建立 Core / Stress / Manual Lab 分类；
- 建立 Smoke / Reliability / Database Exception selectors；
- 将 blocking 改为 suite assertion gate policy；
- 支持 `passed / failed / inconclusive` suite outcome；
- reliability replicate 不增加 independent scenario denominator；
- gate 和分母由 versioned projector 从 EvalRun 明细推导，不写回 AssertionResult；
- CLI adapter 使用独立 ExitPolicy 映射 `inconclusive` 退出码，Evaluator 不感知 CLI/CI。

#### P5：Diagnostic / Markdown / LangFuse Adapters

- 消费 M27A 已生成的安全 EvalRun JSON artifact；
- Markdown 从结构化 artifact 渲染；
- 各 assertion view 使用 `eligible = passed + failed + not_observed`、`observed = passed + failed`；
- 分开报告 execution、semantic、manual evidence 和 gate；
- 移除含义混乱的单一 diagnostic 总分；
- LangFuse score adapter 只回写 observed assertion results 和明确的 reliability 状态；
- projector version 写入报告，JSON 明细可重算出相同汇总；
- M27 不实现新的人工 verdict / 二审工作流。

#### P6：Legacy 冻结、旧测试退场与入口切换

- 标记旧 formal / challenge / diagnostic 为 legacy / read-only；
- 保持历史产物路径不变；
- 如 audit 仍需旧结构，提取最小 legacy adapter；
- `eval.run_eval` 最终只走新 `Evaluator.evaluate()` Interface；
- 新测试覆盖稳定后，删除或迁移只验证旧 runner/scorer 内部细节的测试；
- 只保留必要的 legacy artifact 只读测试；
- 不长期维护两套可新增 case 的 runner 或两套测试模型。

#### 用户确认门 B：正式切换

在新 runner 取代旧入口前向用户展示：

- 迁移后 scenario / assertion / selector 数量；
- 分母示例；
- manual、unavailable、expected rejection 和 gate 示例；
- 旧/new 报告字段映射；
- 已知不兼容点。

#### P7：M27B 验收、确定性验证与新基线决策

- 完成 focused tests、相关回归和全仓 pytest；
- 只使用 fake client / 冻结 trace / SQLite oracle 验证 runner、scorer 和报告；
- 从 EvalRun 明细重算 projector 汇总并与 Markdown/LangFuse payload 对账；
- 验证所有非 completed artifact（含遗留 running/abandoned）不进入 gate；
- 不默认运行真实 LLM 完整 Core / Stress；
- 确定性门禁通过后再说明新基线的运行范围、预计调用数和成本。

#### 用户确认门 C：真实 LLM 新基线

只有用户单独授权后，才以 `m27-v1` 运行新的真实 LLM 基线。第一次运行是新合同事实锚点，不与旧 `25/32`、`26/32` 等数字作升降比较。

## 14. 测试策略

### 14.1 Contract / Loader

- 非法 `Scenario`、typed `AssertionContract`、`EvalRunSpec` 必须失败；
- 重复 scenario / assertion id、selector 引用不存在 scenario 必须失败；
- assertion kind 与其专属字段不匹配时必须失败，例如 `sql_result` 缺少 oracle 定义；
- expected-rejection 断言与普通成功断言存在不可满足冲突时必须失败；
- 分别测试 `catalog_hash`、`selected_contract_hash`、`suite_policy_hash`、`run_spec_hash`；
- hash 对注释、文件路径、YAML key 顺序和纯格式变化稳定，对真实语义变化敏感；
- 未选中 Scenario 变化只影响 catalog hash，不污染本轮 selected contract / run spec hash；
- SQL 只做保守空白归一化，不把可能不同义的 SQL 折叠为同一 hash。

### 14.2 Runner

- 每个 `(run_id, scenario_id, replicate_id)` 最多调用一次 `PipelinePort`；
- 同一业务问题的多个 assertion 共用一份 `ExecutionEvidence`；
- `RunEnvironment` 每轮只创建/清理一次，candidate 与 reference oracle 使用同一 `RunSnapshot`；
- requested/resolved runtime identity 正常对账，显式 mismatch 在首个 Scenario 前失败；
- retry 正确记录 physical attempts，timeout 不产生伪造 SQL；
- pipeline rejection、pipeline error、external unavailable 以中性执行事实落盘；
- scorer、projector 不得隐式再次调用 pipeline、LLM 或数据库；
- running manifest、幂等 checkpoint、run id 防覆盖和最终 `EvalRun` 原子写入均可验证；
- 可捕获中断落为 interrupted/failed；硬崩溃遗留 running 被读取为 incomplete/abandoned；
- `ExecutionEvidence` 不依赖 Markdown parser。

### 14.3 Scorer

- Result 正确/错误、投影错误、alias、顺序和 tolerance；
- SchemaContext alternatives 正反例；
- JoinPath 缺边、错边、真实外键与桥接去重；
- QueryPlan tables/joins/metrics/filter/group/order 正反例；
- Trace 缺步骤、错状态、错顺序、allowed skipped；
- typed assertion 只能 dispatch 到对应 scorer；
- assertion 未配置时不生成结果；已配置但证据缺失时输出 `not_observed` 和明确 reason；
- expected rejection 通过断言判断 pass / fail，而不是新增执行状态；
- assertion 结果不包含 `gate_effect` 等 suite policy 字段；
- scorer 是纯比较函数，不调用 LLM、SQL pipeline、数据库或 seed。

### 14.4 Denominator / Report

- `eligible = passed + failed + not_observed` 恒成立；
- `observed = passed + failed` 恒成立；
- `unavailable` 只是 `not_observed` 的原因切片，不额外加入分母；
- 未配置 assertion 属于 ineligible，不伪造 `not_applicable` 结果；
- manual / diagnostic assertion 是否进入 gate 只由 suite policy projector 决定；
- provider success 不受 semantic fail 影响；
- unavailable 不进入 semantic wrong；
- replicate 不增加 independent scenario count；
- 同一 `EvalRun` 经过同版本 projector 得到的 Markdown / LangFuse 核心计数一致；
- 所有汇总都可由 `ScenarioRun + AssertionResult` 重算，不依赖 `EvalRun` 内的重复计数；
- CLI ExitPolicy 只消费 gate result，不进入 EvalRunSpec 或改变 projector 事实；
- Diagnostic view 不触发新执行或新的人工作业状态机。

### 14.5 Artifact / Evidence

- `contract_version / artifact_schema_version / projector_version` 可独立变化和校验；
- projector 拒绝未知 artifact schema version；
- 长期 evidence bundle 经脱敏且不包含完整 rows、凭证或敏感 provider payload；
- 删除 raw trace 后，自动 scorer 仍可从长期 bundle 重算，SQL/结构化差异仍可复核；
- 所有非 completed artifact 均被 projector/gate 拒绝。

### 14.6 Legacy

- 旧 report / triage / audit artifacts 不被覆盖；
- legacy adapter 只能读取冻结输入；
- 新 scorer 不重算旧分数；
- 文档中历史路径仍可访问；
- 旧实现细节测试在对应新接口测试覆盖后删除或迁移，不长期双轨维护。

## 15. 验收标准

### 15.1 M27A 验收

1. 每个业务问题只有一个 canonical `Scenario`，多个评测维度由 typed assertions 表达；
2. 每个 `(run_id, scenario_id, replicate_id)` 至多一次 pipeline 调用；
3. RunEnvironment 唯一持有并清理 snapshot，candidate 与 reference oracle 共享同一实例；
4. `ExecutionStatus`、`AssertionStatus`、not-observed reason 边界清晰，无 suite policy 泄漏；
5. 所有正式 assertion 都有真实 scorer 和正反测试，不存在默认 `ok`；
6. requested / resolved runtime identity 可对账，显式不一致在首个 Scenario 前失败；
7. scorer 是纯函数，运行中断时已有 checkpoint 可读，硬崩溃遗留 running 不会被视为 completed；
8. 长期安全 evidence bundle 不依赖 raw trace 永久存在，也不持久化完整结果行或明显敏感字段；
9. 四类 hash 与三个 version 各自职责明确并通过稳定性测试；
10. 代表场景垂直切片先通过，再批量迁移正式 scorer/case；
11. 新 contract、environment、port、evidence、scorer 接口测试通过，并能替代对应旧实现细节测试。

### 15.2 M27B 验收

1. manual / diagnostic / blocking 不再混算，gate 完全由 suite policy projector 派生；
2. `eligible = passed + failed + not_observed`、`observed = passed + failed` 可机械验证；
3. provider reliability 按 logical execution / physical attempts 统计，不使用整题 pass 冒充；
4. Markdown 与 LangFuse adapter 消费同一安全 `EvalRun` 和同版本 projector，核心计数一致；
5. diagnostic 输出保留 assertion 级证据与 reason，但不建立新的人工 verdict / review 状态机；
6. CLI ExitPolicy 与 EvalRunSpec 分离，不改变 gate fact；
7. 旧 `m26-v1` 及更早产物保持只读可查，legacy adapter 不进入新门禁；
8. 新入口切换完成，已被新接口测试覆盖的旧实现细节测试完成迁移或删除；
9. focused tests、相关回归、全仓 pytest 和 `git diff --check` 通过；
10. 未经用户确认不运行新的完整真实 LLM 基线，不切模型、retrieval、embedding、fusion、oracle、数据库或可靠性默认值。

## 16. 风险与约束

| 风险 | 影响 | 控制措施 |
|---|---|---|
| 把近似问题误合并 | 不同产品合同被迫共享 reference | P0 migration matrix 逐题确认；不只按问题字符串去重 |
| Assertion Interface 过度通用 | YAML 暴露大量内部 scorer 参数，module 变浅 | 先用真实 case 设计少量稳定 assertion kind；复杂性留在实现内部 |
| 新旧 runner 长期并存 | case 和报告继续双轨漂移 | 只允许短期迁移，P6 后新入口单一化；legacy 只读 |
| 自动化 manual 时 oracle 过弱 | 错 SQL 在单 seed 上碰巧通过 | 对 SCD、退款率、递归类目使用反事实 fixture / counterexample |
| 分母看似更复杂 | 使用者重新退回单一总分 | 报告固定展示少量清晰视图，并给出公式和解释 |
| 上游失败导致大量 not_observed | 误以为系统没有失败 | 与 end-to-end gate、provider availability 并列，不隐藏 unavailable |
| Scorer 重复解析大型 trace | 运行与维护成本上升 | ExecutionEvidence 只构建一次，各 scorer 消费结构化字段 |
| RunEnvironment 变成转发层 | 新增名称但 snapshot 所有权仍不清楚 | 让它真实封装 seed、依赖注入、vector index、resolved identity 和 cleanup；否则合并回 Evaluator |
| requested 与实际运行配置漂移 | 不可复现的 run 被误当成可比较基线 | 首个 Scenario 前冻结并对账 ResolvedRuntimeIdentity，显式冲突 fail fast |
| 中断产物被误判为完整 | 半写 JSON 或部分结果进入门禁 | scenario checkpoint + run 状态 + 原子 finalize；projector 默认拒绝未完成 run |
| raw trace 清理后 evidence_ref 失效 | 历史 run 无法重算或复核 | 长期 artifact 保存自足、脱敏的 evidence bundle，raw trace 仅作短期调试证据 |
| artifact 泄露业务数据 | 报告或 LangFuse 含完整行、PII、SQL literal | allowlist、redaction、摘要/hash、provider metadata 白名单 |
| 为兼容历史污染新结构 | 新 Interface 继续携带 `check_type` / `phase3a_blocking` 混合语义 | 新合同 clean break，legacy adapter 隔离 |

## 17. 非目标

- 不为了新基线好看删除困难题或放宽安全策略。
- 不修改数据库结构、seed、指标默认口径或 `result_match` oracle。
- 不切换默认模型、Milvus、embedding、fusion、timeout 或 retry。
- 不把 LLM-as-Judge 作为新体系的默认裁决器。
- 不建设 Web UI、多人审核、人工 verdict / review queue / 仲裁审批、数据库持久化或完整实验平台。
- 不承诺本阶段实现断点续跑；M27A 只保证 crash-safe checkpoint 与可识别的 partial run，resume 作为后续可选能力。
- 不反向修订旧 formal / challenge / diagnostic 报告。
- 不在逐题合同确认前直接批量改写 YAML。
- 不用更多重复真实 LLM run 代替 runner / scorer 合同治理。

## 18. Implementation Checklist

### M27A

- [ ] P0：完成所有当前 case 的 canonical migration matrix
- [ ] 用户确认门 A1：确认逐题 Scenario、typed assertions 和 suite 去向
- [ ] 用户确认门 A2：确认 `EvalRunSpec`、RunEnvironment、ports、snapshot、runtime identity、evidence、状态和 scorer 边界
- [ ] 用户确认门 A3：确认四类 hash、三个 version、crash-safe artifact 与证据保留/脱敏策略
- [ ] P1：定义 `m27-v1` typed contract、严格 catalog loader、四类 hash 和独立版本
- [ ] P2：实现窄 `Evaluator` Interface、RunEnvironment、共享 snapshot、runtime 对账、单次执行和 checkpoint
- [ ] P3a：用已确认代表场景/fixture 打通多断言垂直切片与安全 EvalRun
- [ ] P3b：扩展严格 assertion registry、全部纯 scorer 和 canonical case 迁移
- [ ] P3 验证：运行新 contract / environment / port / evidence / scorer 接口测试，迁移对应旧实现细节测试

### M27B

- [ ] 用户确认门 B1：确认 suite / selector / protocol / gate policy
- [ ] 用户确认门 B2：确认分母公式、projector 版本、CLI ExitPolicy 和 adapter 消费边界
- [ ] 用户确认门 B3：确认 legacy 只读边界、入口切换和旧测试删除清单
- [ ] P4：实现 suite / selector / protocol / gate projector
- [ ] P5：实现 Diagnostic、Markdown、LangFuse adapters，不新增人工 review workflow
- [ ] P6：冻结 legacy，切换 `eval.run_eval` 到单一新 Interface，删除已替代的旧测试
- [ ] P7：运行确定性 focused / related / full pytest 与 artifact 安全验证
- [ ] 用户确认门 C：决定是否运行 `m27-v1` 真实 LLM 新基线
- [ ] 模块完成后执行 `finish-module`
- [ ] 基于 notes 固化内容执行 `finish-docs`
- [ ] 用户人工检查后执行 `accept-module`

## 19. 两轮 Plan Review 修订记录

- `m27-plan-review.md`：分离执行/断言/Gate，改用 typed assertions 与共享 oracle evidence，补齐 checkpoint、脱敏、projector、M27A/B 和 legacy 边界。
- `m27-plan-review-v2.md`：补齐 RunEnvironment 生命周期、requested/resolved 对账、硬崩溃语义、自足 evidence bundle、独立版本/哈希、CLI ExitPolicy、manual 命名和垂直切片顺序。
