# Phase 3A Diagnostic Benchmark Proposal v3 — 审查与优化建议

> 审查对象：[phase3a-diagnostic-benchmark-proposal-v3.md](phase3a-diagnostic-benchmark-proposal-v3.md)
> 对照依据：[phase3a-plan.md](phase3a-plan.md)、[AI_CONTEXT.md](AI_CONTEXT.md)
> 审查日期：2026-07-23

## 总体评价

v3 相比 v1/v2 是一次质的提升：

- 把 `difficult_diagnosis` 从 capability 改为 `case_properties`，消除了"难度"与"能力"的概念混淆
- Check type 从松散的"contains 某个词"收敛为 9 种分级判据，每种有明确的最低验收标准
- 补全了 YAML 示例：`expected_plan`、`expected_schema_context`、`expected_trace_steps`、`accept_paths`、security subtype
- 单表查询 `join_path` 记为 `skipped` 而非省略，语义清晰
- 32 条 case 的 6 capability 覆盖矩阵合理，每个维度都有足够样本量

**结论：方向上完全正确，可以直接作为 benchmark 设计基础。** 以下优化建议按优先级排列，目标是让 proposal 在对接 phase3a-plan M9-M12 施工时零歧义。

---

## P0 — 与 phase3a-plan.md 的对齐缺口（不改会导致施工矛盾）

### P0-1：`db_hard_002` 的 `phase3a_blocking=true` 与旧链路 baseline 现实冲突

**现状**：proposal 把设备转化率 case（`db_hard_002`）标为 `phase3a_blocking=true`。

**问题**：phase3a-plan M8 验收门写的是"困难 1/3 正确且 3/3 可诊断"——意味着 3 条 `difficult_diagnosis` 不要求全部通过。challenge baseline 实际结果 11/16，`db_hard_001` 和 `db_hard_003` 已知失败且 `review_required=true`。如果 `db_hard_002` 在新链路上也不稳定，把它标为 blocking 会制造一个 M12 无法通过的硬门。

**建议**：二选一：

- **方案 A（推荐）**：`db_hard_002` 保持 `blocking=true`，但在 M12 验收标准中明确"困难诊断 case 的硬门为 1/3 正确 + 3/3 可诊断（有 trace/issue tag）"，与 phase3a-plan 口径一致。
- **方案 B**：改为 `phase3a_blocking=false`，把行为漏斗验证降级为 `quality_win` 观察项，不阻塞 M12 通过。

### P0-2：`local_schema_prompt` 能力覆盖偏弱且缺乏跨域多样性

**现状**：proposal 中 `local_schema_prompt` 只有 7 条 case，且集中在三个窄场景：

| case | 场景 | 表数 |
|---|---|---|
| `db_multi_002` | 类目/商品/明细 Join | 3-4 表 |
| `db_multi_004` | 商品销售额 Top 5 | 3 表 |
| `db_hard_003` | SCD 历史售价 | 2 表 |
| `db_schema_001` | 商品列表+类目 | 2 表 |
| `db_schema_003` | 宽表 vs 星型选择 | 1-2 表 |
| `db_prompt_001` | 商品销售额 Top 5（prompt 验证） | 3 表 |
| `db_prompt_002` | SCD 历史售价（prompt 验证） | 2 表 |

**问题**：
1. `db_hard_003` 和 `db_prompt_002` 围绕同一 SCD 场景，相当于同一能力测了两次
2. 缺少**优惠券多对多**和**行为日志**场景的 prompt 精简验证
3. phase3a-plan P0 要求"局部 Schema prompt 比全量 schema 更小且不丢关键上下文"——需要跨业务域证明这不是巧合

**建议**：新增 1 条 `db_prompt_003`：

```yaml
- id: db_prompt_003
  task_type: local_schema_prompt
  question: 各优惠券类型带来的 GMV 是多少？
  expected_tables: [coupons, order_coupons, orders]
  expected_schema_context:
    must_include_tables: [coupons, order_coupons, orders]
    max_tables: 5
    must_include_columns: [coupon_type, coupon_code, order_amount, paid_at]
    must_include_join_keys: [coupon_id, order_id]
    must_not_include_tables: [knowledge_docs, user_behavior_log, product_price_history, tickets]
  phase3a_capabilities: [local_schema_prompt, join_path]
  phase3a_blocking: true
  check:
    type: schema_context_size
```

这样 `local_schema_prompt` 覆盖三类不同 Join 拓扑：简单外键（商品-类目）、多对多桥接（优惠券）、SCD 时间窗口（价格历史），8 条 case 更有说服力。

### P0-3：`pipeline_mode` 字段在 proposal YAML 示例中缺失

**现状**：phase3a-plan.md 明确要求 `EvalCase.pipeline_mode`（值为 `baseline` / `new_text2sql`），M8 已落地此字段。proposal 的 YAML 字段建议表和所有示例中都没有出现。

**建议**：在 YAML 字段建议表中增加一行：

| 字段 | 是否建议 | 说明 |
|---|---|---|
| `pipeline_mode` | 必填 | `baseline` 跑旧链路、`new_text2sql` 跑新 pipeline；首次 diagnostic baseline 全用 `baseline`，后续 M12 对照跑两轮 |

并在关键 YAML 示例中补上 `pipeline_mode: new_text2sql`。

---

## P1 — 结构性优化（不改也能跑，改了更结实）

### P1-1：`db_schema_003` 多答案 case 缺乏一致性校验

**现状**：`db_schema_003`（宽表 vs 星型模型）使用 `match_mode=any_alternative`，只检查选表是否命中 `[orders_wide]` 或 `[channels, orders]` 之一。

**问题**：如果选了宽表路径但 GMV 算错（比如没过滤 `paid_at`），仍被判通过——因为只要表集合命中就算 `schema_context_match`。多答案 case 变成了"免费通过"。

**建议**：增加隐含一致性约束——不管走哪条路径，关键列和指标必须覆盖。YAML 改为：

```yaml
- id: db_schema_003
  task_type: schema_retrieval
  question: 用看板口径查看 2026 年 6 月各渠道 GMV
  expected_tables_alternatives:
    - tables: [orders_wide]
      required_columns: [channel_name, gmv, snapshot_at]
    - tables: [channels, orders]
      required_columns: [channel_name, order_amount, paid_at, channel_id]
  expected_columns: [channel_name, gmv]        # 不管哪条路径都必须有
  phase3a_capabilities: [schema_retrieval, local_schema_prompt]
  phase3a_blocking: false
  case_properties: [multi_answer, wide_table_choice]
  check:
    type: schema_context_match
    match_mode: any_alternative
    # ★ 关键：匹配到某条 alternative 后，仍需校验其 required_columns
    alternative_must_include_columns: true
```

### P1-2：`db_plan_003` 的 `accept_paths` 需要防止"LLM 总是拒答"的退化

**现状**：`db_plan_003`（知识库文档 × 订单的非法 Join）接受两条路径：`llm_rejected`（LLM 自己判断无法关联）或 `plan_validated`（LLM 生成非法 Join 后被 `validate_query_plan()` 拦截）。

**问题**：如果 LLM 对所有无法关联的表都走 `llm_rejected` 路径，`invalid_join_path` issue tag 永远不会在端到端 benchmark 中出现。benchmark 会失去区分"plan validation 拦截了错误 Join"和"LLM 碰巧拒答了"的能力。

**建议**：在 proposal 中增加两层防护：

1. **benchmark 端到端**：`db_plan_003` 保持两条 `accept_paths`，但 M12 报告必须展示 `blocked_via` 分发比例。如果 100% 都是 `llm_rejected` → 标记为 ⚠️，说明 plan validation 未被端到端验证到。
2. **M10 planner 单测**：必须用 fixture 覆盖确定性的 `invalid_join_path`（不依赖 LLM），直接构造一个包含非法 Join 的 `QueryPlan` 输入到 `validate_query_plan()`，验证返回 `PlanValidationResult(is_valid=False, issue_tags=["invalid_join_path"])`。

proposal 已提到"确定性测试应放在 M10 planner 单测 fixture 中"，但没有明确这是一个 **P0 验收项**。建议在"待确认问题 5"中把它从"是否接受"升级为"M10 必须做到"。

### P1-3：`includes` 策略应该现在拍板，不等下一轮

**现状**：proposal 把 `includes` 作为"待确认问题 4"，推迟到审查后决定。

**问题**：`includes` 的设计会影响 YAML loader 的改动范围，而 loader 改动在 M8 范围内。如果现在不拍板，M8 的 loader 扩展可能要做两遍（先兼容 benchmark 字段，再加 `includes`）。

**建议**：推荐务实方案——**现在就用 `source_case_id` + 独立维护 + 轻量一致性检查**：

1. `phase3a-diagnostic-benchmark.yaml` 独立维护 32 条，每条继承 case 标注 `source_case_id`
2. 在 `eval/run_eval.py` 中加一个 `--check-consistency` flag，加载 benchmark YAML 时校验：
   - 所有 `source_case_id` 引用的 case 在 challenge YAML 中确实存在
   - 关键字段（`question`、`expected_tables`、`task_type`）与来源一致
3. `includes` 语法（`includes: [eval/cases/database-upgrade-challenge.yaml]`）作为后续增强，等 loader 需要支持更复杂的评测组合时再做

这个检查只需约 20 行代码，但能防止三份 YAML 独立维护时的 drift。在 proposal 的"待确认问题 4"中直接改为推荐结论。

### P1-4：`db_plan_001` 与 `db_multi_003` 共享问题的 drift 风险

**现状**：两条 case 共享同一自然语言问题（"2026 年 6 月各渠道 GMV 排名"），`db_multi_003` 从结果层验证，`db_plan_001` 从 plan 结构层验证。

**问题**：challenge YAML 中的 `db_multi_003` 有 `expected_sql`（结果层参考答案），benchmark 中的 `db_plan_001` 有 `expected_plan`（结构层参考答案）。如果未来有人修改了 challenge 中的 `expected_sql`（比如调整 GMV 口径），benchmark 中的 `expected_plan.metrics` 可能不会同步更新，导致两条 case 的隐含口径出现 drift。

**建议**：在 proposal 中加一条约束：共享问题的 case 对，`expected_plan.metrics` 的口径必须与 challenge `expected_sql` 中的聚合表达式一致。M12 对照报告应交叉校验这两条 case 的结果——如果 `db_multi_003` 通过但 `db_plan_001` 失败（或反之），说明 plan 和 SQL 之间存在 gap，值得单独分析。

---

## P2 — 增强建议（让 benchmark 更有面试说服力）

### P2-1：指定 2-3 条 "golden path case" 作为 M12 报告的明星案例

**现状**：32 条 case 平等对待，M12 报告按 capability 维度汇总。

**问题**：面试中最有说服力的证据不是 32 条的统计数字，而是一条完整的诊断链——**同一个问题在旧链路失败 → 新链路通过，并且能逐步骤解释为什么。** 如果 32 条中只有 5 条 `direct_win` 但分散在不同 case 上，讲起来没有冲击力。

**建议**：在 proposal 中明确指定 2-3 条 golden path case，它们在 M12 报告中享受"完整对比剖面"：

| golden path | 为什么选它 | M12 报告展示内容 |
|---|---|---|
| `db_core_001`（GMV） | 最核心指标，面试必讲 | 全量 schema vs 局部 schema 的表/字段数对比、plan 结构、8 个 trace step 时间线 |
| `db_multi_003`（渠道 GMV 排名） | 三表 Join，能展示 JoinPath 价值 | 旧链路"LLM 猜 Join" vs 新链路"relations.yaml 约束 Join"的对比 |
| `db_hard_001`（递归类目 GMV） | 最能证明诊断能力 | 旧链路失败原因 → 新链路 issue tag → 为什么仍标记 `review_required` |

这三条 case 的对比剖面可以**直接截图放进简历附录或面试 PPT**，比 capability 汇总表更有说服力。

### P2-2：补充 `improvement` 分类的计算规则（伪代码）

**现状**：proposal 定义了 5 种 improvement 但没写清楚：一条 case 同时标了多个 capability 时，`direct_win` 算在谁头上？

**建议**：在 proposal 的"改进分类"章节后追加判定逻辑：

```text
improvement 计算规则（M12 报告生成器使用）：

for each case in diagnostic benchmark (32条):
    old_result = baseline_run[case.id]
    new_result = new_pipeline_run[case.id]

    # 1. 先判定 case 级别的 improvement
    if old_result.failed and new_result.passed:
        case_improvement = "direct_win"
    elif old_result.passed and new_result.passed:
        if new_result has better trace/schema/plan than old_result:
            case_improvement = "quality_win"
        else:
            case_improvement = "no_regression"
    elif old_result.failed and new_result.failed:
        if new_result has clearer issue_tag or trace:
            case_improvement = "diagnosability_win"
        else:
            case_improvement = "no_change"
    else:  # old passed, new failed
        case_improvement = "regression"

    # 2. 按 capability 维度分别统计
    for each capability in case.phase3a_capabilities:
        capability_stats[capability][case_improvement] += 1

# 3. 报告输出两种视图：
#    - 按 case 的 improvement 分布（32 条各自属于哪类）
#    - 按 capability 的 improvement 分布（每个 capability 下有几条 direct_win/quality_win/...）
```

关键澄清：**一条 case 的 `direct_win` 会同时计入它标明的所有 capability**。例如 `db_core_001` 标了 `[schema_retrieval, query_plan, trace_steps]`，如果旧失败新通过，三个 capability 各 +1 `direct_win`。这不是重复计数——因为同一条 case 确实同时在三个维度上证明了新链路价值。

### P2-3：`db_prompt_001` 和 `db_multi_004` 实际上是同一问题的两个视角，建议合并或明确分工

**现状**：

| case | question | task_type | capability |
|---|---|---|---|
| `db_multi_004` | 2026 年 6 月商品销售额 Top 5 | `multi_table` | `schema_retrieval, local_schema_prompt` |
| `db_prompt_001` | 2026 年 6 月商品销售额 Top 5 | `local_schema_prompt` | `local_schema_prompt, join_path` |

两条 case 问题完全一样，但分属不同 task_type、不同 check。

**问题**：这和 `db_plan_001`/`db_multi_003` 的"同问题分层验证"是同样的设计模式，但 proposal 没有明确说明这一意图。如果不解释清楚，读者会以为是重复。

**建议**：在 proposal 的 32 条 case 表中，为 `db_prompt_001` 增加说明列："与 `db_multi_004` 同问题；`db_multi_004` 从结果层验证，`db_prompt_001` 从 prompt 结构层验证（schema 大小 + 必须包含字段）"。与 `db_plan_001`/`db_multi_003` 的设计模式保持一致。

### P2-4：缺少 `chart_decision` trace step 的显式覆盖

**现状**：phase3a-plan M11 验收门要求"图表成功时记录 `chart_decision`"，但 32 条 benchmark 中没有一条 case 显式验证 `chart_decision` trace step。

**建议**：在 `db_trace_001`（GMV 单表查询）的 `expected_trace_steps` 中增加可选步骤：

```yaml
- id: db_trace_001
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: skipped}
    - {step_type: query_plan, status: success}
    - {step_type: plan_validation, status: success}
    - {step_type: sql_generation, status: success}
    - {step_type: sql_guard, status: success}
    - {step_type: sql_execution, status: success}
    # chart_decision 是可选的：只在图表成功触发时校验
    # 不强制要求每次 GMV 查询都生成图表
  check:
    type: trace_steps_complete
    min_required_steps: 8
    allow_skipped: [join_path]
    optional_steps:           # ★ 新增
      - {step_type: chart_decision, status: success}
```

同时在 check type 表中为 `trace_steps_complete` 增加 `optional_steps` 说明：这些 step 出现时必须 status 正确，不出现也不扣分。

---

## P3 — 小修小补（建议顺手改了）

### P3-1：能力覆盖矩阵缺少失败模式统计

当前矩阵只统计"覆盖了哪些 case"，没有统计"哪些 case 专门测这个能力的失败模式"。例如 `query_plan` 有 15 条 case，但其中只有 `db_plan_002`（不存在字段）、`db_plan_003`（非法 Join）、`db_plan_004`（多 step 拦截）是测失败路径的。同理，`schema_retrieval` 15 条 case 中没有一条专门测**过度召回**（retrieval 返回了明显无关的表）。

**建议**：在能力覆盖矩阵表中增加一列"失败模式 case"，显式列出每个 capability 的负面测试覆盖：

| capability | 覆盖 case | 失败模式 case |
|---|---|---|
| `schema_retrieval` | 15 | 可增加 1 条过度召回检测（从 `db_prompt_001` 的 `must_not_include_tables` 覆盖） |
| `join_path` | 11 | `db_plan_003`（非法 Join）、`db_hard_001`（递归类目无法自动 Join） |
| `query_plan` | 15 | `db_plan_002/003/004`（不存在字段/非法 Join/多 step） |
| `security_guard` | 4 | 全部 4 条都是失败模式（拦截验证） |

如果不想加 case，至少标注：`schema_retrieval` 的过度召回验证依赖 `db_prompt_*` 的 `must_not_include_tables` 字段，而不是独立 case。

### P3-2：`db_hard_003` 和 `db_prompt_002` 的 SCD 双 case 应明确分工

两条 case 都围绕 SCD 历史售价，且都标 `phase3a_blocking=false` + `case_properties: [manual_review, difficult_diagnosis]`：

| case | task_type | check |
|---|---|---|
| `db_hard_003` | `difficult_diagnosis` | 继承 challenge 的 `expected_sql` + `manual` |
| `db_prompt_002` | `local_schema_prompt` | `schema_context_size` |

**建议**：在 proposal 的 case 说明中明确分工——`db_hard_003` 验证"SCD 时间窗口的 SQL 是否正确"，`db_prompt_002` 验证"SCD 场景的局部 schema 是否包含 `valid_from`/`valid_to` 且不包含无关表"。两者不重复，是同一个难题的 SQL 层和 prompt 层验证。

### P3-3：check type 表中 `manual` 缺少明确的通过/失败判定

当前 `manual` 的说明是"结构化报告里 `review_required=true`"。但没有说明它算 pass 还是 fail。

**建议**：在 check type 表中明确：

| check type | 通过条件 | 说明 |
|---|---|---|
| `manual` | 不参与自动 pass/fail | 跑完生成结构化结果 + `review_required=true`，由人工在 M12 报告中判断；不计入通过率分子分母，单独列出 |

---

## 总结：v3 → v4 改动清单

如果要在 v3 基础上生成 v4（最终版），改动范围如下：

| 优先级 | 编号 | 改动 | 影响范围 |
|---|---|---|---|
| **P0** | P0-1 | `db_hard_002` blocking 校准：保持 `true` + M12 验收标准明确困难 case 1/3 硬门 | case 表 + M12 验收标准 |
| **P0** | P0-2 | 新增 `db_prompt_003`（优惠券多对多 prompt 精简） | case 表 + 能力覆盖矩阵 |
| **P0** | P0-3 | YAML 字段建议表补 `pipeline_mode` | 字段表 + YAML 示例 |
| **P1** | P1-1 | `db_schema_003` 多答案一致性校验增强 | case YAML 示例 |
| **P1** | P1-2 | `db_plan_003` accept_paths 退化防护 + M10 单测 P0 化 | case 说明 + 待确认问题 5 |
| **P1** | P1-3 | `includes` 策略拍板（`source_case_id` + 一致性检查） | Includes 策略章节 + 待确认问题 4 |
| **P1** | P1-4 | `db_plan_001`/`db_multi_003` drift 防护约束 | case 说明 |
| **P2** | P2-1 | 指定 3 条 golden path case | case 表 + M12 报告建议 |
| **P2** | P2-2 | 补 improvement 计算伪代码 | 改进分类章节 |
| **P2** | P2-3 | `db_prompt_001`/`db_multi_004` 同问题分工说明 | case 表 |
| **P2** | P2-4 | `db_trace_001` 补 `optional_steps: [chart_decision]` | trace YAML 示例 + check type 表 |
| **P3** | P3-1 | 能力覆盖矩阵补"失败模式"列 | 能力覆盖矩阵 |
| **P3** | P3-2 | SCD 双 case 分工说明 | case 表 |
| **P3** | P3-3 | `manual` check 通过条件明确 | check type 表 |

**核心原则：v4 不推翻 v3 的主体结构。** 32 条三层结构、6 capability、5 improvement、9 check types 全部保留。以上改动只做对齐、补漏和加固。
