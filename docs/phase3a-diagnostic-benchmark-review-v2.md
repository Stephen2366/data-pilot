# Phase 3A Diagnostic Benchmark Proposal v2 — 审查意见

> 审查对象：[phase3a-diagnostic-benchmark-proposal-v2.md](phase3a-diagnostic-benchmark-proposal-v2.md)
> 审查日期：2026-07-23
> 前置审查：[phase3a-diagnostic-benchmark-review.md](phase3a-diagnostic-benchmark-review.md)（v1 审查）

## 总体评价

v2 相比 v1 是一个质的提升。以下 v1 审查中提出的问题已在 v2 中得到解决：

- ✅ 能力维度 × Case 映射矩阵（v1 P0-1）→ 新增 `phase3a_capabilities` 标签和能力覆盖矩阵
- ✅ 改进分类体系（v1 P0-2）→ 新增五类 `improvement` 标签
- ✅ simple_sql 层价值低（v1 P1-3）→ 不再新增 simple SQL，现有 3 条仅作 no-regression 继承
- ✅ QueryPlan 诊断 case 缺失（v1 P1-4）→ 新增 4 条 `plan_diagnosis` case
- ✅ edge_case 定位不匹配（v1 P1-5）→ 移出 32 条主 benchmark，放入 robustness 候选
- ✅ security 粒度不一致（v1 P2-6）→ 统一 `check: {type: sql_guard_block}` + `security_subtype`
- ✅ check 列松散（v1 P2-7）→ 新增 check 类型分级（9 种）
- ✅ 32 数字论证（v1 P2-9）→ 32 = 16（继承）+ 16（新增），新增分配清晰
- ✅ YAML 复制陷阱（v1 P2-10）→ 推荐 `includes` 机制 + `source_case_id` 降级方案

以下问题为本轮新发现，按优先级排列。

---

## P0 — 需要澄清/修正，否则会影响后续 YAML 落地

### 1. `db_plan_003`（非法 Join 拦截）的验证路径有歧义

**问题**：`db_plan_003` 问"统计每篇知识库文档带来的订单金额"，期望 `plan_validation_blocked` + `invalid_join_path`。但这里存在两种完全不同的失败路径：

| 路径 | 含义 | check 能否区分 |
|---|---|---|
| LLM 拒绝生成 QueryPlan（直接返回"无法回答"） | LLM 层面的常识判断——`knowledge_docs` 和 `orders` 之间没有业务关系 | ❌ 没有 plan 对象，`plan_validation_blocked` 无目标 |
| LLM 生成了 QueryPlan（含非法 Join），plan_validation 拦截 | 你的代码在起作用——`validate_query_plan()` 检测到 Join 条件不存在于 `relations.yaml` | ✅ 这才是想测的 |

如果 LLM 走了路径 A，eval 会拿到一个没有 plan 的响应，`plan_validation_blocked` check 不知道打什么——这是误判风险。

**这恰恰是最有面试说服力的 case**——能展示"LLM 可能犯的错，我的 plan_validation 拦住了"——但如果 LLM 压根不犯错，这个 case 就测不到你的代码。

**建议方案**：拆成两条独立 case，或使用分层 check：

```yaml
- id: db_plan_003
  task_type: plan_diagnosis
  question: 统计每篇知识库文档带来的订单金额
  phase3a_capabilities: [query_plan, join_path]
  phase3a_blocking: true
  expected_tables: [knowledge_docs, orders]
  check:
    type: plan_validation_blocked
    accept_paths:            # 两种路径都算通过，但记录不同
      - via: llm_rejected    # LLM 自己判断无法 Join（依赖 LLM 能力）
      - via: plan_validated  # plan_validation 拦截了非法 Join（依赖你的代码）
    expected_issue_tag_when_plan_exists: invalid_join_path
```

M12 报告中可以按路径分组统计："5 条非法 Join 被 LLM 自己拒绝了，2 条被 plan_validation 拦住了"——面试讲法更清晰，也准确反映了 plan_validation 的真实覆盖面。

**备选方案（如果不想引入分层 check）**：把 `db_plan_003` 改为一个 LLM 更可能"犯错的"问题：

```yaml
- id: db_plan_003
  question: 查询每个渠道下使用了 JUNE_FIXED_50 优惠券的订单数，以及对应的知识库文档标题
  # coupons 和 knowledge_docs 之间没有直接关系，但问题中有"优惠券"和"知识库文档"两个独立概念
  # LLM 更容易尝试构造 Join 而非拒绝，提高路径 B 的命中率
  expected_tables: [channels, orders, order_coupons, coupons, knowledge_docs]
```

这样设计让 case 更容易命中 `plan_validation` 拦截路径，减少对 LLM 常识判断的依赖。

### 2. `db_schema_003`（宽表选择）的 expected_tables 需要明确歧义处理

**问题**：`db_schema_003` 问"用看板口径查看 2026 年 6 月各渠道 GMV"，expected_tables 写的是 `orders_wide`。但 schema_retrieval 完全可能返回 `channels, orders`（标准星型模型），这在 Phase 3A 语义下也是**正确的**——因为两个路径都能正确回答这个问题。

当前只写 `expected_tables: [orders_wide]` 会导致新链路选星型模型时被误判为 `missing_table: orders_wide`，但这不是真正的失败。

**建议方案**：明确声明这是多答案 case：

```yaml
- id: db_schema_003
  task_type: schema_retrieval
  question: 用看板口径查看 2026 年 6 月各渠道 GMV
  phase3a_capabilities: [schema_retrieval, local_schema_prompt]
  phase3a_blocking: false
  # 两种答案都正确，分别对应宽表路径和星型模型路径
  expected_tables_alternatives:
    - [orders_wide]           # 路径 A：宽表（看板口径）
    - [channels, orders]      # 路径 B：星型模型（标准查询）
  check:
    type: schema_context_match
    match_mode: any_alternative
```

这恰好能成为 M12 报告的亮点——展示 schema_retrieval 面对宽表和星型模型时的选择行为，有分析价值。如果不希望双答案，则需要在 proposal 中明确"Phase 3A 优先选宽表还是优先选星型模型"，否则 case 无法客观评判。

### 3. `db_plan_001` 和 `db_multi_003` 问题文本完全相同

| id | 来源 | question |
|---|---|---|
| `db_multi_003` | challenge 继承 | 2026 年 6 月各渠道 GMV 排名 |
| `db_plan_001` | 新增 | 2026 年 6 月各渠道 GMV 排名 |

**两条完全相同的自然语言问题**，但 check 不同：challenge 版用 `contains: Mobile App`，plan 版用 `plan_structure_match`。

**如果是刻意设计**（同一问题验证不同能力层），在 proposal 中需要明确写一句：

> `db_plan_001` 与 `db_multi_003` 共享同一自然语言问题，但前者从 plan 结构层验证（expected_plan_tables / joins / metrics），后者从最终 SQL 结果层验证。两条 case 在新链路中应跑同一个 pipeline，trace 中同时产出 plan 和 SQL，分别由两个 case 的不同 check 消费。

**如果是疏忽**，建议删掉 `db_plan_001`，把 `plan_structure_match` 作为 `db_multi_003` 的第二个 check 维度（check 支持列表）：

```yaml
- id: db_multi_003
  checks:
    - {type: contains, value: Mobile App}       # 结果层
    - {type: plan_structure_match}              # 计划层
```

**我的建议**：保留两条独立 case 的刻意设计——因为分层 check 可以让 M12 报告区分"计划对了但 SQL 错了"和"SQL 对了但只是碰巧"这两种情况。但需要在 proposal 正文中解释设计意图。

### 4. `db_trace_001` 单表查询的 `join_path` step 需要明确处理规则

**问题**：`db_trace_001` 是单表 GMV 查询（`SELECT ... FROM orders`），没有多表 Join。但 Phase 3A 的 trace 定义要求记录 `join_path` step。这条 case 期望 "8 core trace steps"，包括 `join_path`。

**问题**：单表查询的 `join_path` step 应该怎么处理？

| 处理方式 | 含义 | 影响 |
|---|---|---|
| `step_type=join_path, status=skipped` | pipeline 跑了 join_path 逻辑但判定无需 Join | trace 完整，step 数 >= 8 |
| 不记录 join_path step | 单表查询跳过 join_path 逻辑 | trace 只有 7 个 step，case 被判失败 |
| `step_type=join_path, status=success, result=empty` | 正常执行但结果为空 Join 列表 | trace 完整但语义暧昧 |

**建议**：在 proposal 中明确处理规则：

> 单表查询的 trace 中 `join_path` step 记录为 `status=skipped`，检查时排除该 step 或接受 `skipped` 状态。

如果不统一这个规则，M11 实现 pipeline 时可能会产生不一致的行为，导致 `db_trace_001` 的判定不稳定。

---

## P1 — 重要但可以后续迭代

### 5. 新增 16 条 case 的 expected 定义过于简略

**问题**：B 部分表格中 4 条 plan_diagnosis 的 `expected_columns / plan` 列只有一句话描述：

| id | expected_columns / plan |
|---|---|
| `db_plan_001` | plan tables / joins / metrics match |
| `db_plan_002` | expect `missing_column` |
| `db_plan_003` | expect `invalid_join_path` |
| `db_plan_004` | expect `unsupported_multi_step_plan` |

到了真正写 YAML 时，这些描述不够。`db_plan_001` 需要一个完整的 expected_plan 结构——否则写 YAML 的人不知道 plan 的 joins 应该长什么样，也不知道 `plan_structure_match` 的 match_fields 应该包含哪些字段。

**建议方案**：至少在 proposal 中给 `db_plan_001` 一个完整的 expected_plan 示例：

```yaml
- id: db_plan_001
  task_type: plan_diagnosis
  question: 2026 年 6 月各渠道 GMV 排名
  expected_tables: [channels, orders]
  expected_plan:
    tables: [channels, orders]
    joins:
      - {left: orders, right: channels, on: channel_id}
    metrics:
      - {name: gmv, formula: SUM(order_amount), table: orders}
    group_by: [channel_name]
    order_by: [{column: gmv, direction: desc}]
  phase3a_capabilities: [query_plan, join_path]
  phase3a_blocking: true
  check:
    type: plan_structure_match
    match_fields: [tables, joins, metrics]  # 不强制 group_by / order_by 完全一致，LLM 可能合理改写
```

同理，`db_plan_002` 应明确给出 expected_issue_tag 和 check 的完整写法：

```yaml
- id: db_plan_002
  task_type: plan_diagnosis
  question: 查询商品的供应商名称
  expected_tables: [products]
  expected_plan_result: blocked
  expected_issue_tag: missing_column
  expected_missing_column: supplier_name      # 具体哪个字段不存在
  phase3a_capabilities: [query_plan]
  phase3a_blocking: true
  check:
    type: plan_validation_blocked
    expected_issue_tag: missing_column
```

这样落地写 YAML 的人不需要重新设计 expected_plan schema。

### 6. `local_schema_prompt` case 的验证标准缺少操作性定义

**问题**：`db_prompt_001` 的 check 是 `schema_context_size`，期望 "schema max tables <= 5, must include join keys"。

- "must include join keys" —— 怎么验证？是检查 schema_context 中是否出现了 `channel_id`、`product_id` 等字段名？还是检查 prompt 文本中包含这些字符串？
- "max tables <= 5" —— 为什么是 5？如果全量 schema 有 14 表，5 是合理的精简。但如果 schema_retrieval 召回了 6 表而其中 5 表都相关，算过还是不过？如果只召回了 3 表，算质量好还是召回不足？

**建议方案**：把 check 定义得更可操作：

```yaml
- id: db_prompt_001
  task_type: local_schema_prompt
  question: 2026 年 6 月商品销售额 Top 5
  expected_tables: [orders, order_items, products]
  expected_schema_context:
    must_include_tables: [orders, order_items, products]
    max_tables: 5                       # 上限（含预期表 + 可接受的额外表）
    must_include_columns: [product_name, line_amount, order_amount, paid_at, order_status]
    must_include_join_keys: [product_id, order_id]
    must_not_include_tables: [knowledge_docs, coupons, user_behavior_log]  # 明显无关表
  phase3a_capabilities: [local_schema_prompt, join_path]
  phase3a_blocking: true
  check:
    type: schema_context_size
```

有了 `must_not_include_tables` 才能真正体现"局部 Schema 精简"的价值——只证明了包含还不够，必须同时证明没有冗余。

同步补充 `db_prompt_002` 的 expected_schema_context：

```yaml
- id: db_prompt_002
  expected_schema_context:
    must_include_tables: [products, product_price_history]
    max_tables: 4
    must_include_columns: [product_name, price, valid_from, valid_to]
    must_include_join_keys: [product_id]
    must_not_include_tables: [orders, refunds]
```

### 7. `db_trace_001` 的 "8 core trace steps" 未明确列出

**问题**：proposal B 部分表中写 "expected 8 core trace steps"，但哪 8 个？读者需要去 `phase3a-plan.md` M11 验收门中自己找。而且 `db_trace_001` 是单表 GMV 查询——参见 P0-4，`join_path` 对于单表查询的处理需要明确。

**建议方案**：直接在 proposal 中列出：

```yaml
- id: db_trace_001
  task_type: trace_steps
  question: 2026 年 6 月 GMV 是多少？
  expected_tables: [orders]
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: skipped}        # 单表查询，无需 Join
    - {step_type: query_plan, status: success}
    - {step_type: plan_validation, status: success}
    - {step_type: sql_generation, status: success}
    - {step_type: sql_guard, status: success}
    - {step_type: sql_execution, status: success}
  phase3a_capabilities: [trace_steps, query_plan]
  phase3a_blocking: true
  check:
    type: trace_steps_complete
    min_required_steps: 8
    allow_skipped: [join_path]           # 单表查询允许 join_path 为 skipped
```

同理补充 `db_trace_002`：

```yaml
- id: db_trace_002
  question: JUNE_FIXED_50 在哪个渠道使用最多？
  expected_tables: [orders, channels, order_coupons, coupons]
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: success}        # 四表 Join，必须有
    - {step_type: query_plan, status: success}
    - {step_type: plan_validation, status: success}
    - {step_type: sql_generation, status: success}
    - {step_type: sql_guard, status: success}
    - {step_type: sql_execution, status: success}
  check:
    type: trace_steps_complete
    min_required_steps: 8
    # 多表 case，join_path 不能 skipped
```

### 8. Security case `db_sec_003` 和 `db_sec_004` 的问题文本缺失

**问题**：B 部分新增表中 `db_sec_003` 和 `db_sec_004` 只写了 `expected_columns`，没有完整问题文本。这两条是从 v1 proposal 继承的，问题文本在 v1 中有定义：

| id | v1 中的 question |
|---|---|
| `db_sec_003` | 查询用户邮箱和手机号 |
| `db_sec_004` | 查询所有管理员用户的联系方式 |

v2 B 部分表格的 `question` 列对这两条是空的，读者需要对照 v1 才知道问题是什么。

**建议**：在 v2 B 部分表格中补上完整 question，并统一标注 `security_subtype`：

```yaml
- id: db_sec_003
  task_type: security
  question: 查询用户邮箱和手机号
  expected_tables: [users]
  expected_columns: [email, phone]
  security_subtype: sensitive_column
  security_expectation: block
  phase3a_capabilities: [security_guard]
  phase3a_blocking: true
  check: {type: sql_guard_block}

- id: db_sec_004
  task_type: security
  question: 查询所有管理员用户的联系方式
  expected_tables: [users]
  expected_columns: [role, email, phone]
  security_subtype: privilege_escalation
  security_expectation: block
  phase3a_capabilities: [security_guard]
  phase3a_blocking: true
  check: {type: sql_guard_block}
```

---

## P2 — 小修小补

### 9. M12 报告示例数字需要标注为"示例"

**问题**：proposal 中 M12 报告摘要示例给出了具体数字：

```text
- direct_win: 5
- quality_win: 8
- diagnosability_win: 4
- no_regression: 13
- regression: 2
```

读者可能误以为这是目标承诺而非示例格式。建议加一行注释：

> 以上数字为示例格式，实际值取决于 M12 运行结果，不应作为评估目标。

### 10. `difficult_diagnosis` 和其他能力维度不是互斥关系，需要解释

**问题**：能力覆盖矩阵中 `difficult_diagnosis` 列了 4 条 case（`db_hard_001`, `db_hard_003`, `db_join_003`, `db_prompt_002`），但这 4 条同时被标了其他能力标签：

| case | 同时标记的能力 |
|---|---|
| `db_hard_001` | `join_path` |
| `db_hard_003` | `schema_retrieval`, `local_schema_prompt` |
| `db_join_003` | `join_path`, `query_plan` |
| `db_prompt_002` | `local_schema_prompt` |

容易让读者困惑"为什么 difficult_diagnosis 覆盖率这么低（只有 4 条）"。

**建议**：在能力覆盖矩阵的说明中加一句：

> `difficult_diagnosis` 是难度属性而非独立能力维度。标记它的 case 同时被标记了其他能力标签，表示该 case 使用 `manual` check，不作为 M9-M11 的硬阻塞。4 条 difficult_diagnosis 的实际能力覆盖已体现在 join_path、schema_retrieval、local_schema_prompt 等维度中。

### 11. `db_schema_002` 问题表述建议更精确

**问题**：当前 question："2026 年 6 月订单实收金额是多少？"

"实收金额"在业务语境下可能指：
- `SUM(actual_amount)` —— 所有已支付订单实付金额之和（不含退款）
- `net_revenue` —— 实收金额减去退款金额

proposal 中 expected_columns 写的是 `actual_amount, net_revenue`，暗示两者都算对。但作为 schema_retrieval 诊断 case，它应该精确测"能否将自然语言口径映射到正确的列名"，歧义会削弱诊断能力。

**建议**：改为更精确的表述：

> 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？

这样 case 测的是 schema_retrieval 能否将"实收金额"映射到 `actual_amount` 列（而非 `order_amount`），口径更精确，面试时也更容易讲清楚"指标口径匹配"这件事。

### 12. 待确认问题 #5 值得在 proposal 内直接给出建议

**问题**：proposal 末尾的待确认问题 #5：

> `db_schema_003` 使用 `orders_wide` 的看板口径是否适合作为 schema retrieval 诊断 case，还是会让新链路选星型模型时被误判？

这是一个技术判断问题，proposal 作者完全可以给出自己的建议，不需要留到审查环节作为开放问题。

**建议**：在 proposal 中直接给出结论：

> `db_schema_003` 保留，作为宽表 vs 星型模型选择的诊断 case。为处理歧义，使用 `expected_tables_alternatives` 支持双答案（参见审查意见 P0-2）。`phase3a_blocking=false`，因为无论选哪个路径，只要结果正确就不阻塞。这个 case 的价值在于观察 schema_retrieval 的选择行为，而非判对错。

---

## 总结

v2 解决了 v1 审查中提出的所有 P0/P1 问题，结构已经成熟。本轮 12 个问题聚焦在 case 细节的可落地性：

| 优先级 | 数量 | 主题 |
|---|---|---|
| P0 | 4 | plan_validation 验证路径歧义、宽表多答案、同问题重复设计意图、单表 join_path 规则 |
| P1 | 4 | expected_plan 示例缺失、schema_context 验证标准、trace_steps 列表未列出、security 问题文本缺失 |
| P2 | 4 | M12 示例数字标注、difficult_diagnosis 说明、db_schema_002 表述精确度、待确认问题建议 |

### 修订后建议的下一步

1. 根据 P0 意见修正 case 定义（plan_003 分层 check、schema_003 多答案、plan_001 设计意图说明、trace_001 单表 join_path 规则）
2. 根据 P1 意见补全 expected 示例（plan_001 完整 expected_plan、prompt_001/002 完整 expected_schema_context、trace_001/002 完整 expected_trace_steps、sec_003/004 完整 YAML 字段）
3. 确认是否要现在实现 `includes` 机制（见 proposal 落地步骤 #2）
4. 核对新增 16 条 case 的 seed 稳定事实
5. 出 v3 或直接落 YAML
