重新读取后，上一轮提出的核心问题基本都已吸收。新版 [m27-plan.md](D:/.Work/Practice/AI-Project/data-pilot/docs/notes/m27-plan.md) 已经补齐状态代数、typed assertion、oracle seam、增量 checkpoint、脱敏、接口收紧和 M27A/B 里程碑，整体已经具备实施条件。

仍建议补充以下几点。

## P0：最好在实施前明确

### 1. 明确 Run Snapshot 的所有者和生命周期

现在 `PipelinePort` 与 `OraclePort` 分开注入，但计划只要求它们“共享同一 snapshot”，还没有说明谁负责：

- 创建 seed/counterfactual；
- 把同一个 engine/fixture 注入 FastAPI；
- 提供给 reference SQL；
- 在整轮结束后释放；
- snapshot 创建失败时如何结束 run。

建议增加内部 `RunEnvironment` 或等价对象，由 Evaluator 在一轮开始时创建并持有：

```
RunEnvironment
├── resolved runtime identity
├── pipeline access
├── oracle access
├── snapshot identity
└── lifecycle / cleanup
```

不一定要把它变成新的外部 Port，但这个所有权必须唯一，否则两个 adapter 仍可能各自创建 seed。

### 2. 冻结“实际解析配置”，不能只记录请求配置

历史 A/B 最大风险之一就是配置看似相同、实际模型或 Milvus collection 不同。

建议在 run 开始时记录并验证：

- requested / resolved provider 与模型；
- pipeline mode；
- retrieval backend、fusion；
- embedding provider/model/dimension；
- Milvus collection、row count、schema docs hash；
- oracle fixture/hash；
- timeout/retry 的实际值。

`run_spec_hash` 可以表示“想跑什么”，但 artifact 还必须保存“实际跑了什么”。二者不一致时应立即失败或明确标记，而不是继续生成可比较报告。

### 3. 修正硬崩溃时的 run 状态描述

计划要求崩溃后 partial artifact 标记为 `interrupted`，但进程被直接杀死时，没有机会写这个状态。

建议改为：

- 开始前先原子写入 `run_status=running` 的 manifest；
- 每个场景写幂等 checkpoint；
- 正常完成后写 `completed`；
- 主动捕获的中断可写 `interrupted`；
- 硬崩溃遗留的 `running` 在下次读取时视为 `abandoned/incomplete`，不得进入 projector 或 gate；
- Resume 尚未实现时，同一 `run_id` 再次启动应拒绝还是新建，必须明确。

### 4. 解决 evidence 引用与长期保留的矛盾

计划中长期 EvalRun 只保存脱敏 sample、hash 和 `evidence_ref`，但 raw trace 位于 gitignored 的 `eval/traces/`，未来可能被清理。届时 hash 只能证明“曾经有某份文件”，不能重新人工审查。

需要明确选择：

- 长期保存一份脱敏但足以复核的 evidence bundle；或
- raw evidence 有明确保留期限；或
- 只承诺 AssertionResult 可验证，不承诺未来重新人工判 SQL。

建议长期保存：完整候选/reference SQL 的安全表示、完整结果的规范化 hash、行数、结构化 diff，以及必要的脱敏反例；raw rows 可以不保存。

## P1：重要但可在 P1/P2 落地时处理

### 5. 把 CLI/CI 的退出策略移出 EvalRunSpec

`EvalRunSpec` 当前包含“CLI/CI 对 inconclusive 的处理策略”。这属于调用方行为，不是评测事实。

建议：

- EvalRunSpec 保存 Gate Policy；
- Projector 产出 `passed/failed/inconclusive`；
- CLI adapter 决定 inconclusive 时退出码是 0 还是非 0。

否则 Evaluator 的 Interface 会知道 CLI/CI 细节，降低 module 的 locality。

### 6. 给 artifact 单独设置 Schema Version

`m27-v1` 是 case contract version，但 EvalRun JSON 结构未来可能独立演化。

建议分别记录：

- `contract_version`
- `artifact_schema_version`
- `projector_version`

这样修改 JSON 字段不需要假装业务 case 合同也发生变化。

### 7. 区分完整 Catalog Hash 与本轮合同 Hash

如果 `contract_hash` 对整个 catalog 计算，那么修改一个未被本轮 selector 选中的场景，也会让当前 Core run 的 hash 改变。

建议明确：

- `catalog_hash`：全部 canonical scenarios；
- `selected_contract_hash`：本轮实际选中的 Scenario + assertions；
- `suite_policy_hash`
- `run_spec_hash`

这样既能追踪完整 catalog，又不会让无关场景变化污染本轮可重复性。

### 8. Manual View 的命名仍有轻微冲突

计划明确“不建设 review queue”，但分母章节仍使用 `review_pending`。这个词容易让人以为已经存在持久化人工任务。

建议在 M27 中改为：

- `manual_evidence_required`，或
- `manual_not_observed`

未来真正建设 review workflow 后，再把它映射为 `review_pending`。

## P2：实施方式优化

### 9. M27A 先做一个垂直切片，再批量迁移

不要先定义所有结构、再一次性实现全部 scorer。建议先用一个包含多种 assertion 的代表场景打通：

```
typed Scenario
→ 一次 PipelinePort
→ 同 snapshot reference
→ Result + Context + Plan + Trace
→ checkpoint
→ EvalRun
```

确认 Interface、证据和 artifact 形状稳定后，再迁移全部 case。这样更容易在真实使用中发现设计过度或字段缺失。

## 结论

目前没有需要推翻总体方案的问题。最值得再补进计划的是：

1. **Run Snapshot 的唯一所有者与清理生命周期**；
2. **requested 与 resolved runtime identity 对账**；
3. **硬崩溃留下 `running` artifact 的处理规则**；
4. **raw evidence 被清理后如何保持长期可审计**；
5. **CLI 退出策略移出 EvalRunSpec**；
6. **artifact schema version 与 selected contract hash**。

其中前四项直接影响新基线是否可信，建议在进入 P1/P2 编码前确定。