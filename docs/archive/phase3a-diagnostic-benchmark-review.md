# Phase 3A Diagnostic Benchmark Proposal — 审查意见

> 审查对象：[phase3a-diagnostic-benchmark-proposal.md](phase3a-diagnostic-benchmark-proposal.md)
> 审查日期：2026-07-23

## 总体评价

Proposal 的三层评测结构（regression → challenge → diagnostic）和"不把 M9-M11 变重、M12 用来证明价值"的策略是正确的。以下问题按优先级排列，P0 建议先修再落地，P1 建议落地前调整，P2 可在实施中迭代。

---

## P0 — 结构性问题，建议先修再落地

### 1. 缺少「能力维度 × Case」映射矩阵

**问题**：proposal 按 SQL 复杂度分类（simple_sql / core_metric / multi_table / difficult / edge / security），但 Phase 3A 要证明的核心能力是：

> schema_retrieval → join_path → query_plan → local_schema_prompt → trace_steps → security

当前 32 条没有一条标注"这条 case 主要测哪个 Phase 3A 新能力"。结果是：M12 对照报告只能输出"通过率从 X 变成 Y"，但无法回答**面试官会问的那个问题**——"新链路到底改进了什么？"

**建议方案**：给每条 case 加一个 `phase3a_capability` 标签（可多个），按能力维度分配覆盖：

| capability | 建议覆盖 case 数 | 说明 |
|---|---|---|
| `schema_retrieval` | 6-8 | 验证检索正确选择表/字段/指标，含表名歧义（products vs product_price_history）和口径选择（order_amount vs actual_amount） |
| `join_path` | 4-5 | 验证多表 Join 路径来自 `domain_pack/schema_desc/relations.yaml`，不靠 LLM 自己猜 |
| `query_plan` | 5-6 | 验证 plan 结构正确 + 自检拦截不存在字段/非法 Join/敏感字段/多 sql_query step |
| `local_schema_prompt` | 3-4 | 验证局部 Schema prompt 比全量 Schema prompt 精简（表/字段数量对比有数据支撑） |
| `trace_steps` | 3-4 | 验证 8 种 step_type 完整记录，每步含 step_index/step_type |
| `security_guard` | 4 | 验证 DDL/DML 语法层拦截 + 敏感字段语义层拦截 |

每条 case 在 YAML 中加一个字段，示例：

```yaml
- id: db_multi_001
  question: JUNE_FIXED_50 在哪个渠道使用最多？
  phase3a_capabilities: [schema_retrieval, join_path, query_plan]
  # schema_retrieval: 需要正确选择 orders/channels/order_coupons/coupons 四表
  # join_path: 验证 orders→channels (channel_id)、orders→order_coupons (order_id)、order_coupons→coupons (coupon_id) 来自 relations.yaml
  # query_plan: 验证 plan 中的 joins 列表与 SchemaGraph 一致
```

### 2. 缺少「改进分类」体系

**问题**：proposal 说"展示更多失败类型、改进类型和 trace 质量"，但从未定义改进类型。没有这个分类，M12 对照报告就只是两张通过率表格，讲不出"新链路价值"的故事。

**建议方案**：在 proposal 中明确定义五类改进标签：

| 类型 | 标签 | 含义 | 面试价值 |
|---|---|---|---|
| **Direct Win** | `improvement:direct_win` | 旧链路失败 → 新链路通过 | ⭐⭐⭐ 直接证明新链路更强 |
| **Quality Win** | `improvement:quality_win` | 两者都通过，但新链路 trace 清晰、Schema 更精简（如全量 50+ 字段 → 局部 8 字段） | ⭐⭐ 证明可诊断性 |
| **Diagnosability Win** | `improvement:diagnosability_win` | 两者都失败，但新链路有 issue tag 可定位（如 `missing_column`、`invalid_join_path`） | ⭐ 证明可维护性 |
| **No Regression** | `improvement:no_regression` | 两者都通过 | 基线保障 |
| **Regression** | `improvement:regression` | 旧链路通过 → 新链路失败 | ⚠️ 需要修的 bug |

M12 对照报告分组展示时，按这五类做统计摘要，面试时能一句话说清楚："32 条 benchmark 中，新链路直接解决了旧链路 5 个失败 case，在 12 个两者都通过的 case 上提供了精简 60% 的局部 Schema 和完整 trace。"

---

## P1 — 重要优化，建议落地前调整

### 3. simple_sql 层（4 条）诊断价值极低

**问题**：4 条全是单表 `SELECT + WHERE`：

| id | 实际 SQL 逻辑 |
|---|---|
| `db_simple_001` | `SELECT ... FROM products WHERE status='active' LIMIT 10` |
| `db_simple_002` | `SELECT ... FROM orders WHERE paid_at BETWEEN ...` |
| `db_simple_003` | `SELECT ... FROM coupons WHERE coupon_code = 'JUNE_FIXED_50'` |
| `db_simple_004` | `SELECT ... FROM refunds ... LIMIT 10` |

这些不涉及 schema_retrieval 决策（没有表名歧义）、不涉及 join_path、不涉及 query_plan 自检。对证明 Phase 3A 新能力贡献为零——它们测的是 LLM 的基础 SQL 能力，不是你的中间层。

**建议方案**：砍到 2 条，腾出名额给更有诊断价值的 case。保留的 2 条应改为"简单但有诊断意义"的场景：

- **替换 db_simple_001**：问"查询商品列表"时，schema_retrieval 需要在 `products` vs `product_price_history` vs `product_categories` 中正确选择 `products`（验证检索决策）
- **替换 db_simple_002**：问"查询订单金额"时需要正确选择 `order_amount`（下单金额）还是 `actual_amount`（实付金额）——这测的是 metrics.yaml 口径匹配

`db_simple_003` 和 `db_simple_004` 的直接单表查询能力已在 challenge 的 core_metric/multi_table case 中附带覆盖，可删除。

### 4. 缺少显式的 QueryPlan 诊断 case

**问题**：Phase 3A 的 P0 交付之一是 QueryPlan/QueryPlanStep，但 32 条 proposal 中没有任何一条验证"计划是否正确"。所有 case 只看最终 SQL 是否包含某个字符串——完全绕开了计划层。

**当前 check 方式的盲区**：`contains: gmv` 只能验证 SQL 文本里出现了 "gmv" 这个词，不能验证：
- plan 中的 `tables` 列表是否来自 SchemaGraph
- plan 中的 `joins` 条件是否来自 relations.yaml
- plan 中的 `metrics` 是否与 metrics.yaml 口径一致
- plan_validation 是否真的拦截了非法计划

**建议方案**：新增 3-4 条 `plan_diagnosis` 类 case，替换砍掉的 simple_sql：

```yaml
# 示例 1：验证合法计划结构
- id: db_plan_001
  task_type: plan_diagnosis
  question: 2026 年 6 月各渠道 GMV 排名
  phase3a_capabilities: [query_plan]
  expected_plan_tables: [channels, orders]
  expected_plan_joins:
    - {left: orders, right: channels, key: channel_id}
  expected_plan_metrics: [gmv]
  check: {type: plan_structure_match}

# 示例 2：验证计划自检拦截非法字段
- id: db_plan_002
  task_type: plan_diagnosis
  question: 查询商品的供应商名称
  # 数据库中 products 表没有 supplier_name 字段 → plan_validation 应拦截
  phase3a_capabilities: [query_plan]
  expected_plan_result: blocked
  expected_issue_tag: missing_column
  check: {type: plan_validation_blocked}

# 示例 3：验证多 sql_query step 被拦截
- id: db_plan_003
  task_type: plan_diagnosis
  question: 先查 6 月 GMV，再查退款率，最后对比
  # Phase 3A 不支持多 SQL step → 应返回 unsupported_multi_step_plan
  phase3a_capabilities: [query_plan]
  expected_plan_result: blocked
  expected_issue_tag: unsupported_multi_step_plan
  check: {type: plan_validation_blocked}
```

### 5. dirty_data/edge_case 定位与 Phase 3A 目标不匹配

**问题**：4 条 edge case 测的是数据质量鲁棒性——重复订单号、未支付但有金额、退款超额、孤儿退款。这些与 Phase 3A 的"可检索、可计划、可校验、可追踪"的 Text2SQL 中间层目标正交。proposal 自己的 review question #3 也意识到了这个问题。

**建议方案（推荐方案 A）**：移到独立的 `robustness` 子集，标注 `phase3a_blocking: false`：

```yaml
# 在 YAML 中标注为非阻塞
- id: db_edge_001
  task_type: edge_case
  phase3a_capabilities: [data_quality]  # 非 Phase 3A 核心能力
  phase3a_blocking: false               # M12 不阻塞验收
  question: 查询有外部订单号重复风险的订单
  ...
```

**替代方案（方案 B）**：重新设计为测 plan_validation 的数据质量预检能力：

```yaml
- id: db_edge_001_v2
  task_type: plan_diagnosis
  question: 统计各渠道退款率时，退款中包含 processing 状态的记录吗？
  phase3a_capabilities: [query_plan]
  # 期望：plan 中明确标注 refund_status 过滤条件，或 plan_validation 提示数据质量风险
  expected_plan_conditions: [refund_status]
  check: {type: plan_condition_check}
```

---

## P2 — 锦上添花，可在实施中迭代

### 6. security case 粒度不一致

**问题**：`db_sec_001/002` 测 DDL/DML 语法层拦截（`DROP TABLE`、`DELETE FROM`），`db_sec_003/004` 测列级敏感字段语义层拦截（`email`、`phone`）。它们走的是 SQL Guard 的不同代码路径，pass/fail 标准不同。

proposal 中 `db_sec_003/004` 的 check 写的是"block 或敏感字段拦截/越权拦截"——与已有 regression YAML 中 `check: {type: sql_guard_block}` 格式不一致。

**建议方案**：统一为已有格式，并加 `security_subtype` 区分拦截层级：

```yaml
- id: db_sec_001
  task_type: security
  security_subtype: ddl_block        # 语法层：DDL 拦截
  check: {type: sql_guard_block}
  security_expectation: block

- id: db_sec_002
  task_type: security
  security_subtype: dml_block        # 语法层：DML 拦截
  check: {type: sql_guard_block}
  security_expectation: block

- id: db_sec_003
  task_type: security
  security_subtype: sensitive_column # 语义层：敏感字段拦截
  check: {type: sql_guard_block}
  security_expectation: block

- id: db_sec_004
  task_type: security
  security_subtype: privilege_escalation  # 语义层：越权拦截
  check: {type: sql_guard_block}
  security_expectation: block
```

### 7. "check 建议"列过于松散

**问题**：已有 challenge YAML 每条都有 `expected_sql`，proposal 中大量写 `contains: gmv`——但 SQL 里出现 "gmv" 这个词不等于正确计算了 GMV（可能错用 `order_amount` 而非 `SUM(order_amount)`、可能没过滤 `cancelled` 状态）。

**建议方案**：分级要求：

| case 层级 | check 要求 | 理由 |
|---|---|---|
| core_metric (7条) | `expected_sql` + `expected_result_range` | 固定口径指标，必须有精确答案 |
| multi_table (8条) | `expected_sql` + `contains` 兜底 | Join 路径可验证，聚合结果可能有浮点差异 |
| difficult_diagnosis (5条) | `expected_sql` + `manual` | 作为诊断素材，manual review 可接受 |
| simple_sql (建议缩减后 2条) | `expected_sql` | 简单查询可直接对比 |
| security (4条) | `check: {type: sql_guard_block}` | 不改动 |
| edge_case (4条) | `expected_sql` 或 `manual` | 取决于 seed 稳定性 |

参考已有 challenge YAML 中 `db_core_001` 的写法：

```yaml
- id: db_core_001
  expected_sql: |
    SELECT ROUND(SUM(order_amount), 2) AS gmv
    FROM orders
    WHERE paid_at >= '2026-06-01 00:00:00'
      AND paid_at < '2026-07-01 00:00:00'
      AND order_status NOT IN ('cancelled', 'canceled')
```

### 8. 缺少 TraceStep 质量 case

**问题**：Phase 3A 要求 trace_steps 至少包含 8 种 step_type，但没有一条 case 验证"trace 真的完整产出了这些步骤"。

**建议方案**：选 2 条 core_metric case，加 `expected_trace_steps`：

```yaml
- id: db_core_001
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: success}
    - {step_type: query_plan, status: success}
    - {step_type: plan_validation, status: success}
    - {step_type: sql_generation, status: success}
    - {step_type: sql_guard, status: success}
    - {step_type: sql_execution, status: success}
```

在 M12 对照报告中作为 trace 完整性的实物证据。

### 9. 32 这个数字缺乏论证

**问题**：给人的感觉是 16(challenge) + 16(新增) = 32，但新增的选题逻辑不清晰。实际上 proposal 新增了约 20 条（因为 challenge 已含 simple/core 的部分 case，proposal 中又重复列了一些同问题 case）。

**建议方案**：在 proposal 开头用一段话说明数字来源：

> 32 = 16（challenge 继承，含 10 regression）+ 16（新增）
> 新增 16 条分配：3 条 plan_diagnosis（替换砍掉的 simple） + 3 条 join_path 深度 + 2 条 local_schema_prompt 对比 + 4 条 trace_steps 完整性 + 4 条 security 扩展

### 10. YAML 实施步骤中的复制陷阱

**问题**：实施步骤 #2 说"先复制当前 `database-upgrade-challenge.yaml` 的 16 条"。如果 32 ⊃ 16 ⊃ 10 是严格的包含关系，直接复制会导致同一个 case 的文本在 3 个 YAML 中独立维护，必然 drift（修了一个 YAML 的 expected_sql 忘了修另外两个）。

**建议方案**：二选一——

- **方案 A**：在 eval 框架层支持 `includes` 引用机制（长期更优）
  ```yaml
  # phase3a-diagnostic-benchmark.yaml
  includes:
    - eval/cases/database-upgrade-challenge.yaml  # 继承全部 16 条
  cases:
    # 只写新增的 16 条
    - id: db_plan_001
      ...
  ```

- **方案 B（务实）**：明确承认三套 YAML 各自独立维护，把包含关系降级为"设计意图"而非"技术约束"，在文件头部注释中标注对应的 challenge/regression ID 供人工对照
  ```yaml
  # 本 case 对应 database-upgrade-challenge.yaml 中的 db_core_001
  # 如有修改，请同步更新两处
  - id: db_core_001
  ```

### 11. 其他小问题

| 问题 | 位置 | 建议 |
|---|---|---|
| db_multi_008 和 db_hard_001 递归类目重复 | proposal review question #6 | 将 `db_multi_008` 改为普通一级类目统计，`db_hard_001` 保留递归 CTE |
| db_edge_004 的 seed 依赖未验证 | proposal review question #7 | 先核对 seed 是否存在固定异常事实；如果没有，改为 `manual` 且 `phase3a_blocking: false` |
| db_hard_002（加购转化率）check 写法降级 | proposal difficult_diagnosis 表 | challenge YAML 中已有完整 `expected_sql`，proposal 应引用而非重写为 `contains: mobile_app` |
| db_core_005 在 proposal 中是新增，但 challenge 无此 case | core_metric 表 | 如果是纯新增，需先确认 `order_coupons` 和 `coupons` 表之间的 discount_amount 在 seed 中有稳定事实 |
| db_core_002 和 db_hard_004 退款率概念重叠 | core_metric + difficult_diagnosis | db_core_002 是"退款率最高的商品"（单指标排序），db_hard_004 是"GMV 高且退款率高"（组合诊断）。保留但区分难度标签 |

---

## 总结：建议的 32 条重排方案

按 Phase 3A 能力维度而非 SQL 复杂度组织：

| 能力维度 | case 数 | 来源 | 核心验证点 |
|---|---|---|---|
| **Schema Retrieval** | 6 | 从 core/multi 中选 + 新增表名歧义 case | 表/字段/指标正确命中，含口径选择 |
| **JoinPath** | 5 | 从 multi/hard 中选 + 新增 Join 来源验证 | Join 条件来自 relations.yaml，不靠 LLM 猜 |
| **QueryPlan + Validation** | 6 | **新增** plan_diagnosis case | 计划结构校验、非法字段/Join/多 step 拦截 |
| **Local Schema Prompt** | 4 | 从 multi 中选 + **新增** 对比 case | 局部 Schema 比全量 Schema 精简（字段数对比） |
| **Trace Completeness** | 4 | 从各层抽选 + 加 expected_trace_steps | 8 种 step_type 完整记录 |
| **Security Guard** | 4 | 继承 challenge | DDL/DML 语法层 + 敏感字段语义层双路径 |
| **Difficult Diagnosis** | 3 | 继承 challenge（递归 CTE、SCD、漏斗） | 深度诊断素材，保留 manual review |
| **总计** | **32** | | |

这样 M12 对照报告可以按能力维度逐一展示"新链路改进了什么"，而不是笼统地说"通过率从 X 变成 Y"。

### 建议的落地步骤（修订版）

1. 先在 proposal 中补上能力维度映射矩阵和改进分类体系
2. 确认 32 条的最终名单和每条的能力标签
3. 在 eval 框架中支持 `includes` 引用（或确认各自独立维护）
4. 对每条新增 case 核对 seed 稳定事实后再落 YAML
5. 新建 `eval/cases/phase3a-diagnostic-benchmark.yaml`，先跑旧链路 baseline
6. 把真实结果写回 `AI_CONTEXT.md` 和 `phase3a-plan.md`，不预设通过率
