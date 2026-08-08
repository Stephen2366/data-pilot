总体判断：[m27-plan.md](D:/.Work/Practice/AI-Project/data-pilot/docs/notes/m27-plan.md) 的主方向正确，现状分析也比较准确，尤其抓住了重复执行、占位 scorer 默认通过、混合分母和结构化事实源问题。

但正式实施前仍建议优化以下内容。

## P0：实施前必须补清

### 1. 修正状态模型中的三个冲突

当前把 `expected_rejection` 放进 `ExecutionStatus` 不合适。“是否发生拒绝”是事实，“这个拒绝是否符合预期”是 assertion 判断。

建议改为：

- Execution：`completed / rejected / pipeline_error / external_unavailable`
- Assertion：`passed / failed / not_observed`
- Expected-rejection assertion：判断实际 `rejected` 是否符合预期原因
- Gate：再根据 suite policy 计算 `passed / failed / inconclusive`

同时，`AssertionResult.gate_effect` 应删除。Assertion 是事实，`required/advisory/excluded` 属于不同 suite 的 Gate Policy；否则同一个 assertion 在 Core 和 Stress 中无法复用。

### 2. 统一 `eligible / not_observed / unavailable / not_applicable` 的数学关系

当前计划存在轻微矛盾：

- AssertionStatus 有 `not_observed`；
- 报告又单列 `unavailable`；
- 还要求 `eligible = observed + unavailable + not_applicable`。

建议明确：

```
eligible = passed + failed + not_observed
observed = passed + failed
not_observed_reason = external_unavailable | pipeline_error | missing_evidence
```

没有声明某 assertion 的场景就是 `ineligible`，不需要再生成 `not_applicable` AssertionResult。`not_applicable` 最多保留为跨场景报告视图概念。

### 3. 避免 ScenarioContract 变成“大量可选字段容器”

目前建议把 `expected_tables`、alternatives、columns、metrics、reference SQL、expected plan 全放在 Scenario 顶层，又用 `assertions[]` 声明检查类型。这样容易形成浅 module：每个 scorer 都要理解一大包无关字段。

建议：

- Scenario 顶层只保留题面、身份、业务说明和标签；
- 每个 typed assertion 自己拥有所需合同。

例如：

```
assertions:
  - kind: result_match
    reference_sql: ...
    columns: [...]
  - kind: schema_context
    alternatives: [...]
  - kind: query_plan
    expected: ...
```

共享业务口径可以引用统一 metric 定义，但不要把所有 scorer 参数平铺到 Scenario 顶层。

### 4. 明确 reference oracle 在哪里执行

计划要求 scorer 不访问数据库，但 `result_match` 必须执行 reference SQL。当前实现是在 scorer 内重新创建一套 SQLite seed，这与新设计冲突。

建议规定：

```
Evidence Builder
├── 调用一次 pipeline，取得候选结果
├── 在同一 oracle snapshot 上执行 reference SQL
└── 产出 candidate result + expected result/diff
        ↓
纯 scorer 只比较证据
```

需要保证候选 SQL和 reference SQL 使用相同 seed/snapshot，特别是未来加入 counterfactual 后，不能各自创建不同数据库状态。

### 5. 增加长时间运行的崩溃安全

计划目前主要描述“运行结束后生成 EvalRun JSON”。但真实 diagnostic 经常运行十几到二十分钟，也发生过外层超时和 partial trace。

建议增加：

- 每个 Scenario 完成后增量写入结构化记录；
- run 状态包含 `running / completed / interrupted`；
- 最终 artifact 原子落盘；
- 中断时保留已完成场景，不伪装成完整 EvalRun；
- 是否支持 resume 可以后定，但 partial evidence 必须可用。

## P1：强烈建议调整

### 6. 收紧外部 Interface

当前：

```
evaluate_suite(suite_name, execution_protocol, dependencies)
```

其中 `suite_name` 无法清楚表达 classification、selector、protocol 和 gate policy；`EvalDependencies` 也可能变成庞大的 service locator。

建议改为类似：

```
evaluate(run_spec: EvalRunSpec, pipeline: PipelinePort) -> EvalRun
```

`EvalRunSpec` 冻结 catalog、selector、protocol 和 gate policy；`PipelinePort` 才是实际 seam：

- 生产 adapter：FastAPI/TestClient；
- 测试 adapter：内存 fake。

同时明确“一次执行”的真正不变量：

```
每个 (run_id, scenario_id, replicate_id) 最多调用一次 pipeline
```

Reliability 的多个 replicate 仍会执行多次，但同一 replicate 下所有 assertions 共享证据。

### 7. 不要在 EvalRun 中保存两份统计事实

计划同时保存：

- `AssertionResult[]`
- report view 的原始计数

后者其实可以从前者推导。两份都成为事实源后，可能再次出现 JSON 明细和 Markdown 总数不一致。

建议 EvalRun 只保存原始结果；报告计数由固定版本的 projector 推导。如果为了查询性能保存缓存汇总，需要标记 projector version，并在测试中验证可重算一致。

### 8. 补充结构化 artifact 的脱敏策略

`ExecutionEvidence` 计划保存完整 response 和 trace，但未来可能包含：

- 用户问题；
- SQL；
- 查询结果；
- 邮箱、手机号等敏感字段；
- provider metadata。

需要在实施前确认：

- 哪些字段进入长期 EvalRun；
- 哪些只用 `evidence_ref + hash` 指向原 trace；
- 行结果是全量、hash 还是脱敏 sample；
- LangFuse adapter 能上传什么；
- 安全阻断题不得把敏感结果写进 artifact。

这属于安全和长期证据策略，不能实施时临时决定。

### 9. M27 暂时不要实现新的人工审查流程

用户当前优先处理 diagnostic，人工审查优化准备稍后做。M27 应做到：

- EvalRun 为后续人工审查保留足够证据；
- 旧 M26 audit 继续走 legacy adapter；
- 暂不重新设计人工 verdict、二审、mutation 审查工作流。

计划中的 Human audit adapter 可以保留为预留接口，但不应成为 M27 的主要交付，否则模块范围会进一步膨胀。

## P2：可以边实施边完善

### 10. 考虑拆分交付规模

当前 P0–P7 同时涉及合同、catalog、runner、全部 scorer、状态模型、报告、LangFuse、legacy 和入口切换，规模很大。

建议至少设置两个真正可验收的内部里程碑：

- **M27A**：migration matrix、数据结构、严格 loader、一次执行、真实 scorer、结构化 artifact；
- **M27B**：selector/gate/report/LangFuse、legacy 隔离和正式入口切换。

不一定要拆成两个模块编号，但不要等所有 P0–P7 完成后才第一次整体验收。

### 11. 补充 catalog hash 的规范

需要明确 hash 基于：

- 规范化后的 Scenario/Assertion 内容；
- reference SQL；
- metric contract；
- selector 和 gate policy 是否分别计算 hash；
- YAML 字段顺序、注释和文件路径是否影响 hash。

建议对规范化语义内容计算 hash，避免仅调整 YAML 排版就产生新合同版本。

### 12. 新接口测试应逐步替代旧实现细节测试

按 deep module 原则，新测试应主要通过 `evaluate(...) -> EvalRun` 验证行为。旧 runner/scorer 的实现细节测试在新接口覆盖后应逐步删除或迁移，避免长期维护两套测试模型。

## 推荐结论

最需要在计划中先修改的是：

1. **状态与 Gate 完全分离**；
2. **typed assertion 拥有自己的合同数据**；
3. **明确 oracle evidence 构建位置**；
4. **支持 partial run 的增量结构化落盘**；
5. **收紧为 `EvalRunSpec + PipelinePort` 的深 module Interface**；
6. **M27 只为人工审查预留证据，不展开新的审查体系**。

其余总体架构和实施顺序可以保留。当前计划已经接近可执行，但上述 P0 项如果不先定清，后面很可能在 P2–P5 之间反复修改核心数据结构。