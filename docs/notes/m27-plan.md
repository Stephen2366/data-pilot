# M27 Diagnostic / Eval Case 体系优化计划

> 状态：方案已由用户确认，当前仅完成计划，不实施代码与 case 迁移。
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

推荐让调用方只依赖一个高杠杆入口：

```python
evaluate_suite(
    suite_name: str,
    execution_protocol: ExecutionProtocol,
    dependencies: EvalDependencies,
) -> EvalRun
```

调用方不需要手工编排 catalog、HTTP 调用、trace 读取、scorer 顺序和分母计算。复杂度集中在 module 实现内部，测试也通过同一 Interface 验证。

### 4.2 内部数据流

```text
Scenario Catalog
      │
      ▼
Suite / Selector ──► 唯一 Scenario 列表
      │
      ▼
Scenario Runner ──► 每个 Scenario 一次逻辑执行
      │
      ▼
ExecutionEvidence
      │
      ├── Result Assertion
      ├── Schema Context Assertion
      ├── QueryPlan Assertion
      ├── Trace Assertion
      ├── Safety / Expected-Rejection Assertion
      └── Output Contract Assertion
      │
      ▼
AssertionResult[] + ScenarioRun[]
      │
      ├── JSON artifact（结构化事实源）
      ├── Markdown report adapter
      ├── LangFuse score adapter
      └── Human audit adapter
```

### 4.3 建议的数据结构

#### ScenarioContract

至少包含：

- `scenario_id`
- `question`
- `user_role`
- `business_contract`
- `expected_tables / alternatives`
- `expected_columns / aliases`
- `expected_metrics`
- `reference_sql` 或 expected-rejection 合同
- `assertions[]`
- `tags[]`
- `contract_notes / authority`

业务题面、指标口径和 reference 只在 Scenario 中维护一次。Context、Plan、Trace assertion 不得复制一份不同题面。

#### ExecutionEvidence

至少包含：

- run / scenario / replicate identity；
- pipeline mode、model、retrieval、oracle 和 contract version；
- logical call 与 physical attempts；
- HTTP / provider / transport 状态；
- response body 与完整 trace；
- SchemaGraph、QueryPlan、candidate SQL；
- Guard / Fidelity / execution / output contract 证据；
- latency / token / cost 等可用运行信息。

#### AssertionResult

至少包含：

- `assertion_id / kind`
- `status`
- `reason`
- `issue_tags`
- `evidence_refs`
- `metadata`
- `gate_effect`

`AssertionResult` 不直接覆盖 Scenario 的执行状态，也不把 manual pending 编造成数值 pass。

#### EvalRun

至少包含：

- run identity 与 runtime metadata；
- selector / protocol 快照；
- `ScenarioRun[]`；
- assertion 结果；
- report view 的原始计数；
- suite gate 状态。

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
    contract:
      expected_tables: [channels, orders]
      expected_columns: [channel_name, gmv]
      expected_metrics: [gmv]
      reference_sql: |
        SELECT ...
    assertions:
      - id: semantic_result
        kind: result_match
      - id: schema_context
        kind: schema_context
      - id: query_plan
        kind: query_plan
      - id: trace_complete
        kind: trace_complete
```

具体 YAML 字段在实施前通过 fixture 验证可读性；避免为每个 scorer 暴露大量只有内部实现才需要的参数，使 Scenario Interface 重新变浅。

## 6. Assertion / Scorer 架构

### 6.1 严格注册

建立 `assertion.kind -> scorer` 注册表，并满足：

- catalog 加载时验证所有 kind；
- 未注册 kind 立即报错；
- 禁止默认 `passed=True / ok`；
- 每个 scorer 明确声明所需 evidence；
- scorer 接收依赖，不在内部重新调用 LLM、重新读全局 trace 或创建隐式外部状态。

### 6.2 基础执行事实与业务 assertion 分离

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

### 6.3 不使用早返回掩盖证据

- 上游失败导致证据不存在时，下游 assertion 返回 `not_observed`。
- 已经存在的 Context / Plan / SQL / Result 证据应尽量全部评分。
- scorer 不把“未执行”记为能力失败，也不把“当前不适用”记为通过。
- suite gate 可以因 required assertion 未观察而成为 `inconclusive`，但 semantic view 仍保持 `not_observed`。

### 6.4 当前占位 check 的处置

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
- `expected_rejection`
- `pipeline_error`
- `external_unavailable`

### 7.2 Assertion Status

建议枚举：

- `passed`
- `failed`
- `not_observed`
- `not_applicable`

### 7.3 Review Status

建议枚举：

- `not_required`
- `pending`
- `completed`
- `blocked_by_unavailable`

### 7.4 Gate Policy / Gate Result

Gate policy：

- `required`
- `advisory`
- `excluded`

Suite gate result：

- `passed`
- `failed`
- `inconclusive`

外部不可用或 required assertion 未观察时，suite 可以 `inconclusive`；CLI/CI 是否 fail-closed 由执行策略决定，不把它改写为 semantic wrong。

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
- `unavailable`：外部或上游失败导致未观察；
- `not_applicable`：本场景不适用；
- `review_pending`：等待人工裁决。

自动能力率只计算：

```text
passed / (passed + failed)
```

同时必须并列展示：

- end-to-end scenario outcome；
- provider availability；
- required assertion gate；
- unavailable 数量和原因。

禁止：

- 把 unavailable 从 end-to-end 报告中删除；
- 把 unavailable 计为 semantic wrong；
- 把 manual pending 计为 passed；
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
- 新报告明确写出 catalog hash / contract version / selector / protocol / oracle / runtime metadata。

### 11.2 旧文件处理

- 不移动、删除、覆盖旧 YAML 和历史报告。
- 在说明文档标记 legacy / read-only，避免继续作为新入口。
- 新 run 不写入旧报告文件名。
- 不为兼容旧报告继续保留混乱的 `EvalCase.check_type` Interface。

### 11.3 结构化事实源

- 新运行先写 JSON artifact，再从 JSON 渲染 Markdown。
- Markdown 不反向参与新评分或汇总。
- LangFuse 回写只消费 AssertionResult，不自行重算。
- Human audit 消费 EvalRun artifact；若需要读取旧历史，走独立 legacy adapter。

## 12. 候选代码落点

最终命名可在实施时按 locality 微调，但应保持一个主要外部 Interface，避免过多浅层文件：

```text
eval/
  contracts.py          # Scenario / Evidence / AssertionResult / EvalRun 稳定结构
  evaluator.py          # evaluate_suite() 深 module
  catalog.py            # 新合同加载、selector 和严格验证
  assertions/           # 内部 scorer adapters 与 registry
  reporting.py          # JSON 事实源与 Markdown / LangFuse 投影
  legacy.py             # 仅冻结历史需要的最小只读 adapter（如确有需要）
  run_eval.py           # CLI adapter，最终切到 evaluate_suite()

eval/cases/m27/
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

如果实际实现发现上述拆分产生只转发参数的浅层 module，应合并回 `evaluator.py` 或 `catalog.py`，以 Interface 深度和 locality 为准，不以目录整齐为目标。

## 13. 实施阶段

### P0：冻结范围与建立迁移账本

#### P0-1 全量 case inventory

- 盘点 smoke、formal、challenge、diagnostic extra、exception、reliability 的所有 case；
- 建立 `old_case_id -> scenario_id -> assertions -> classification -> selectors` 矩阵；
- 识别精确重复、题面近似但合同不同、真正独立问题；
- 核对 reference SQL、指标、时间、过滤、排序、LIMIT、alias 和人工 rubric；
- 单列当前无真实 scorer 的 check。

#### P0-2 用户确认门 A：逐题合同迁移

在修改正式 case 前向用户提交：

- canonical scenario 清单；
- 合并/保留/淘汰理由；
- Core / Stress / Manual Lab 去向；
- 每个 Scenario 的 assertions；
- 存在业务歧义或 oracle 风险的题。

用户确认前不改正式题面、reference、分母或 scorer。

### P1：新合同与严格加载器

- 定义 ScenarioContract、AssertionContract、ExecutionProtocol 和 Selector；
- 实现 catalog hash 与 `m27-v1` 版本；
- assertion kind 严格注册，未知 kind 加载失败；
- 检查 duplicate scenario id、duplicate assertion id、悬空 selector、缺 reference、冲突分类；
- 用最小 fixture 验证 schema 易读性和错误信息。

### P2：一次执行与统一证据

- 实现每个 Scenario 一次 logical pipeline 调用；
- 记录 replicate id 与 physical attempts；
- 从同一次 response / JSONL trace 构造 ExecutionEvidence；
- 不允许 scorer 重新调用 pipeline；
- fake client 测试多个 assertions 只触发一次 `client.post()`；
- 外部 timeout、expected rejection、Guard block、SQL execution error 分别形成稳定 execution status。

### P3：Assertion Registry 与真实 scorer

- 迁移 result / expected value / output / safety / expected-rejection；
- 迁移已可信的 SchemaContext alternatives 和 plan-validation scorer；
- 为 metric mapping、JoinPath、QueryPlan structure、Trace completeness 建立真实正反 scorer；
- 每个 scorer 明确 evidence dependency；
- 上游证据缺失返回 `not_observed`；
- manual rubric 不产生自动 numeric pass。

### P4：Suite / Selector / Gate

- 建立 Core / Stress / Manual Lab 分类；
- 建立 Smoke / Reliability / Database Exception selectors；
- 将 blocking 改为 suite assertion gate policy；
- 支持 `passed / failed / inconclusive` suite outcome；
- reliability replicate 不增加 independent scenario denominator。

### P5：结构化报告与 Diagnostic 视图

- 先生成 EvalRun JSON artifact；
- Markdown 从结构化 artifact 渲染；
- 各 assertion view 使用各自的 eligible / observed / pass / fail / unavailable 分母；
- 分开报告 execution、semantic、review 和 gate；
- 移除含义混乱的单一 diagnostic 总分；
- LangFuse score adapter 只回写 observed assertion results 和明确的 reliability 状态。

### P6：Legacy 冻结与入口切换

- 标记旧 formal / challenge / diagnostic 为 legacy / read-only；
- 保持历史产物路径不变；
- 如 audit 仍需旧结构，提取最小 legacy adapter；
- `eval.run_eval` 最终只走新 `evaluate_suite()` Interface；
- 不长期维护两套可新增 case 的 runner。

#### 用户确认门 B：正式切换

在新 runner 取代旧入口前向用户展示：

- 迁移后 scenario / assertion / selector 数量；
- 分母示例；
- manual、unavailable、expected rejection 和 gate 示例；
- 旧/new 报告字段映射；
- 已知不兼容点。

### P7：确定性验证与新基线决策

- 完成 focused tests、相关回归和全仓 pytest；
- 只使用 fake client / 冻结 trace / SQLite oracle 验证 runner、scorer 和报告；
- 不默认运行真实 LLM 完整 Core / Stress；
- 确定性门禁通过后再说明新基线的运行范围、预计调用数和成本。

#### 用户确认门 C：真实 LLM 新基线

只有用户单独授权后，才以 `m27-v1` 运行新的真实 LLM 基线。第一次运行是新合同事实锚点，不与旧 `25/32`、`26/32` 等数字作升降比较。

## 14. 测试策略

### 14.1 Contract / Loader

- 未注册 assertion kind 必须失败；
- 重复 scenario / assertion id 必须失败；
- selector 引用不存在 scenario 必须失败；
- result assertion 缺 reference 必须失败；
- expected-rejection 与普通 allow 合同冲突必须失败；
- catalog hash 对相同内容稳定、内容变化可观察。

### 14.2 Runner

- 一个 Scenario 含四个 assertions 只调用一次 pipeline；
- 两个 replicate 记录为一个独立 Scenario、两次 logical execution；
- retry 正确记录 physical attempts；
- timeout 不产生伪造 SQL；
- expected rejection 与外部失败可区分；
- ExecutionEvidence 不依赖 Markdown parser。

### 14.3 Scorer

- Result 正确/错误、投影错误、alias、顺序和 tolerance；
- SchemaContext alternatives 正反例；
- JoinPath 缺边、错边、真实外键与桥接去重；
- QueryPlan tables/joins/metrics/filter/group/order 正反例；
- Trace 缺步骤、错状态、错顺序、allowed skipped；
- 上游 unavailable 时 assertion 为 `not_observed`；
- manual pending 不贡献 pass；
- scorer 不重新调用 LLM 或 SQL pipeline。

### 14.4 Denominator / Report

- eligible = observed + unavailable + not_applicable 的适用不变量按定义成立；
- passed + failed = observed；
- manual pending 不进入自动 observed 分母；
- provider success 不受 semantic fail 影响；
- unavailable 不进入 semantic wrong；
- replicate 不增加 independent scenario count；
- JSON 与 Markdown 汇总一致；
- Diagnostic view 不触发新执行。

### 14.5 Legacy

- 旧 report / triage / audit artifacts 不被覆盖；
- legacy adapter 只能读取冻结输入；
- 新 scorer 不重算旧分数；
- 文档中历史路径仍可访问。

## 15. 验收标准

M27 完成至少满足：

1. formal / challenge / diagnostic 中同一业务问题在一次评测中最多执行一次；
2. 所有正式 assertion 都有已注册 scorer 和正反测试，不存在默认 `ok`；
3. Result、Context、Plan、Trace、安全使用同一份 ExecutionEvidence 并独立判分；
4. Diagnostic 只是报告视图，不产生额外 LLM 调用；
5. Core、Stress、Manual Lab 职责清楚，Smoke / Reliability / Exception 复用 canonical scenarios；
6. manual pending、pipeline error、external unavailable、semantic wrong 和 expected rejection 可分别统计；
7. blocking 已迁为 suite/gate policy，不再是 Scenario 固有属性；
8. 各能力视图拥有明确的 eligible / observed / pass / fail / unavailable 分母；
9. provider reliability 按 logical execution / physical attempts 统计，不使用整题 pass 冒充；
10. 新运行先产生结构化 EvalRun artifact，Markdown / LangFuse / audit 只作 adapter；
11. 旧 `m26-v1` 及更早产物保持只读，不被新合同重算或覆盖；
12. focused tests、相关回归、全仓 pytest 和 `git diff --check` 通过；
13. 未经用户确认不运行新的完整真实 LLM 基线，不切模型、retrieval、embedding、fusion、oracle、数据库或可靠性默认值。

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
| 为兼容历史污染新结构 | 新 Interface 继续携带 `check_type` / `phase3a_blocking` 混合语义 | 新合同 clean break，legacy adapter 隔离 |

## 17. 非目标

- 不为了新基线好看删除困难题或放宽安全策略。
- 不修改数据库结构、seed、指标默认口径或 `result_match` oracle。
- 不切换默认模型、Milvus、embedding、fusion、timeout 或 retry。
- 不把 LLM-as-Judge 作为新体系的默认裁决器。
- 不建设 Web UI、多人审核、数据库持久化或完整实验平台。
- 不反向修订旧 formal / challenge / diagnostic 报告。
- 不在逐题合同确认前直接批量改写 YAML。
- 不用更多重复真实 LLM run 代替 runner / scorer 合同治理。

## 18. Implementation Checklist

- [ ] P0：完成所有当前 case 的 canonical migration matrix
- [ ] 用户确认门 A：确认逐题 Scenario、assertions 和 suite 去向
- [ ] P1：定义 `m27-v1` contract 与严格 catalog loader
- [ ] P2：实现 Scenario 单次执行与统一 ExecutionEvidence
- [ ] P3：实现严格 assertion registry 和所有正式真实 scorer
- [ ] P4：实现 suite / selector / protocol / gate policy
- [ ] P5：实现结构化 EvalRun、独立分母和 Diagnostic report views
- [ ] P6：冻结 legacy，切换 `eval.run_eval` 到单一新 Interface
- [ ] 用户确认门 B：确认正式入口、分母和不兼容迁移
- [ ] P7：运行确定性 focused / related / full pytest 验证
- [ ] 用户确认门 C：决定是否运行 `m27-v1` 真实 LLM 新基线
- [ ] 模块完成后执行 `finish-module`
- [ ] 基于 notes 固化内容执行 `finish-docs`
- [ ] 用户人工检查后执行 `accept-module`
