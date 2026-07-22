# Phase 3A Diagnostic Benchmark Proposal v4

> 目的：给新会话或外部审查者评审 Phase 3A 诊断评测扩展方案。本文是 **proposal v4**，不是已落地执行计划；当前项目仍只实际维护 `10` 条 formal regression 和 `16` 条 challenge baseline。

## v4 修订摘要

v3 已经把 proposal 推到可落 YAML 的程度。v4 继续吸收 `phase3a-diagnostic-benchmark-review-v3.md` 的对齐审查，重点处理 Phase 3A plan 施工时会遇到的边界和 drift 风险。

- 保留 `10 formal / 16 challenge / 32 diagnostic benchmark` 三层结构，总数仍为 32。
- 保留 v3 的 capability / improvement / case_properties / check type 主体。
- 新增 `pipeline_mode` 字段说明：baseline 跑旧链路，`new_text2sql` 跑新 pipeline；runner 可覆盖，但报告必须记录实际模式。
- 用 `db_prompt_003` 替换低价值的新增 `db_schema_001`，让 `local_schema_prompt` 覆盖优惠券多对多桥接。
- 强化 `db_schema_003` 多答案 case：每个 alternative 都要带 required columns，不再只匹配表集合。
- 把 `db_plan_003` 的确定性 `invalid_join_path` fixture 写成 M10 P0 验收项，避免端到端 LLM 总拒答导致校验器没被测到。
- 拍板 YAML 维护策略：短期采用 `source_case_id + 独立 YAML + 一致性检查`，`includes` 作为后续增强。
- 增加 golden path、improvement 计算伪代码、失败模式矩阵、manual check 统计规则和可选 `chart_decision` trace step。

## 背景

Phase 3A 的目标不是“多问几条 SQL”，而是证明 Text2SQL 链路从阶段二 v1 变成了可检索、可计划、可校验、可追踪的中间层。M8 已经冻结旧链路 baseline：

- `eval/cases/phase3a-regression.yaml`：`10` 条 formal regression，作为 M8-M12 主硬门。
- `eval/cases/database-upgrade-challenge.yaml`：`16` 条 challenge superset，包含全部 `10` 条 formal question，作为每个模块陪跑的轻量诊断门。
- 旧链路 baseline：formal `8/10` passed；challenge `11/16` passed。

`16` 条 challenge 适合日常开发陪跑，但 M12 如果只报告“通过率从 X 到 Y”，面试和复盘都不够有解释力。v4 的 32 条 benchmark 应服务于一个更清晰的问题：

> 新链路在哪些能力上比旧链路更好：选表选字段、Join 路径、指标口径、计划校验、局部 Schema、Trace 完整性、安全边界，分别改进了什么？

## 建议结论

采用三层评测结构：

| 层级 | 用例数 | 文件建议 | 用途 | 运行频率 |
|---|---:|---|---|---|
| Formal Regression | 10 | `eval/cases/phase3a-regression.yaml` | 主硬门，判断阶段三A核心能力是否达标 | 每模块必跑 |
| Challenge Superset | 16 | `eval/cases/database-upgrade-challenge.yaml` | 轻量诊断门，观察困难题和扩展数据库复杂度 | 每模块必跑 |
| Diagnostic Benchmark | 32 | `eval/cases/phase3a-diagnostic-benchmark.yaml` | 深度诊断集，按能力维度证明新旧链路差异 | M12 必跑；平时手动跑 |

包含关系：

```text
32 diagnostic benchmark
  contains 16 challenge
    contains 10 formal regression questions
```

## 能力维度

`phase3a_capabilities` 建议允许多选，因为一条 case 往往同时验证多个能力。

| capability | 目标 | 典型证据 |
|---|---|---|
| `schema_retrieval` | 正确召回相关表、字段、指标和口径 | expected_tables / expected_columns / expected_metrics 命中 |
| `join_path` | Join 条件来自 `relations.yaml`，不靠 LLM 猜 | trace 中出现合法 JoinPath，关系键正确 |
| `query_plan` | QueryPlan / QueryPlanStep 结构正确，且 plan_validation 可拦截错误 | expected_plan_*、issue tag、Pydantic 校验 |
| `local_schema_prompt` | 局部 Schema prompt 比全量 schema 更小且不丢关键上下文 | schema_context 表数 / 字段数对比 |
| `trace_steps` | 新链路记录完整可诊断步骤 | expected_trace_steps 完整，含 step_index / step_type |
| `security_guard` | DDL/DML、敏感字段、越权字段被拦截 | SQL Guard blocked，security_subtype 清晰 |
`difficult_diagnosis` 不放在 capability 列表中。它是 case 属性，表示这个 case 难度高、通常使用 `manual` 或 `review_required=true`，不作为 M9-M11 的硬阻塞；它的真实能力覆盖仍应落到 `schema_retrieval`、`join_path`、`query_plan`、`local_schema_prompt` 等维度。

## 改进分类

M12 对照报告应从 old baseline 和 new pipeline 两组结果中派生 `improvement`，不要手写在 case 里。

| improvement | 判定 | 用途 |
|---|---|---|
| `direct_win` | 旧链路失败，新链路通过 | 直接证明新链路增强了能力 |
| `quality_win` | 两者都通过，但新链路 schema 更精简、trace 更完整或 plan 更可解释 | 证明可维护性和可诊断性 |
| `diagnosability_win` | 两者都失败，但新链路给出更稳定 issue tag / trace 定位 | 证明失败也可分析 |
| `no_regression` | 两者都通过，且无明显质量退化 | 证明新链路没有破坏旧能力 |
| `regression` | 旧链路通过，新链路失败 | M12 必须列为待修问题 |

M12 报告建议按 capability 和 improvement 做二维摘要，例如：

```text
schema_retrieval: direct_win=3, quality_win=4, no_regression=5, regression=0
join_path: direct_win=2, diagnosability_win=2, regression=1
```

M12 报告生成器建议使用以下计算规则：

```text
for each case in diagnostic benchmark:
    old_result = baseline_run[case.id]
    new_result = new_pipeline_run[case.id]

    if old_result.failed and new_result.passed:
        case_improvement = direct_win
    elif old_result.passed and new_result.passed:
        if new_result.schema_context_smaller_or_trace_better_or_plan_clearer:
            case_improvement = quality_win
        else:
            case_improvement = no_regression
    elif old_result.failed and new_result.failed:
        if new_result.issue_tags_clearer_or_trace_more_complete:
            case_improvement = diagnosability_win
        else:
            case_improvement = no_change
    else:
        case_improvement = regression

    for capability in case.phase3a_capabilities:
        capability_stats[capability][case_improvement] += 1
```

一条 case 可以同时计入多个 capability。例如 `db_core_001` 标记了 `schema_retrieval / query_plan / trace_steps`，如果它是 `quality_win`，三个 capability 都各自增加一次 `quality_win`。这不是重复统计，而是多维归因：同一条 case 同时证明了多个中间层能力。

## YAML 字段建议

Diagnostic benchmark 需要比当前 challenge YAML 多一些诊断字段，但不要把它升级成完整 EvalOps 平台。

```yaml
- id: db_plan_004
  task_type: plan_diagnosis
  pipeline_mode: new_text2sql
  question: 先查 6 月 GMV，再查退款率，最后对比
  phase3a_capabilities: [query_plan, trace_steps]
  phase3a_blocking: false
  expected_plan_result: blocked
  expected_issue_tag: unsupported_multi_step_plan
  check: {type: plan_validation_blocked}
```

字段说明：

| 字段 | 是否建议 | 说明 |
|---|---|---|
| `pipeline_mode` | 必填或 runner 覆盖后必记录 | `baseline` 跑旧链路，`new_text2sql` 跑新 pipeline；首次 diagnostic baseline 全用 `baseline`，M12 对照跑 `baseline` 与 `new_text2sql` 两轮 |
| `phase3a_capabilities` | 必填 | M12 按能力维度汇总 |
| `phase3a_blocking` | 必填 | `true` 表示 M12 失败需要优先修；`false` 表示诊断素材 |
| `case_properties` | 可选 | 难度 / 审查属性，例如 `manual_review`、`difficult_diagnosis`、`multi_answer`、`planner_fixture` |
| `source_case_id` | 可选 | 如果继承自 challenge / formal，记录来源，降低 drift 风险 |
| `source_case_file` | 可选 | 与 `source_case_id` 配套，记录来源 YAML 文件 |
| `security_subtype` | security 必填 | `ddl_block` / `dml_block` / `sensitive_column` / `privilege_escalation` |
| `expected_tables_alternatives` | 多答案 case 必填 | 多条合理选表路径，`match_mode=any_alternative` |
| `expected_plan_*` | plan case 必填 | 验证 plan 层，不只看最终 SQL |
| `expected_schema_context` | prompt case 必填 | 验证局部 schema 表数 / 字段数上限和必须包含内容 |
| `expected_trace_steps` | trace case 必填 | 验证 step_type、status、step_index 等 |

## 32 条 Case v4

### A. 继承 16 条 challenge

这 16 条直接来自 `eval/cases/database-upgrade-challenge.yaml`。v4 建议短期在 benchmark YAML 中独立维护这 16 条，并用 `source_case_id + source_case_file + --check-consistency` 防止与 challenge 源文件 drift；完整 `includes` 机制留到后续 benchmark 组合变多时再实现。

| id | task_type | question | phase3a_capabilities | phase3a_blocking | case_properties | 说明 |
|---|---|---|---|---|---|---|
| `db_simple_001` | simple_sql | 查询 active 商品列表前 10 条 | `schema_retrieval` | true | - | 低权重 no-regression；验证商品表基础召回 |
| `db_simple_002` | simple_sql | 查询 2026 年 6 月已支付订单 | `schema_retrieval` | true | - | 低权重 no-regression；验证订单时间字段 |
| `db_simple_003` | simple_sql | 查询 `JUNE_FIXED_50` 优惠券基本信息 | `schema_retrieval` | true | - | 低权重 no-regression；验证优惠券表和业务键 |
| `db_core_001` | core_metric | 2026 年 6 月 GMV 是多少？ | `schema_retrieval, query_plan, trace_steps` | true | - | 指标口径和 trace 完整性代表 case |
| `db_core_002` | core_metric | 2026 年 6 月退款率最高的商品是什么？ | `schema_retrieval, query_plan` | true | - | 商品退款率口径，区分订单 / 退款关系 |
| `db_core_003` | core_metric | 2026 年 6 月净收入是多少？ | `schema_retrieval, query_plan` | true | - | 区分 `order_amount` 与 `actual_amount` |
| `db_core_004` | core_metric | 各渠道订单量是多少？ | `schema_retrieval, join_path` | true | - | 渠道 Join 基础 case |
| `db_multi_001` | multi_table | `JUNE_FIXED_50` 在哪个渠道使用最多？ | `schema_retrieval, join_path, query_plan` | true | - | 多对多桥接表，验证去重订单数 |
| `db_multi_002` | multi_table | 一级类目销售额排名 | `schema_retrieval, join_path, local_schema_prompt` | true | - | 类目 / 商品 / 明细 Join，不使用递归 |
| `db_multi_003` | multi_table | 2026 年 6 月各渠道 GMV 排名 | `join_path, query_plan, trace_steps` | true | - | result-level case；与 `db_plan_001` 同问题但 check 不同 |
| `db_multi_004` | multi_table | 2026 年 6 月商品销售额 Top 5 | `schema_retrieval, local_schema_prompt` | true | - | 局部 schema 应聚焦订单明细 / 商品 |
| `db_hard_001` | difficult_diagnosis | 数码电子及其子类目 2026 年 6 月 GMV 是多少？ | `join_path` | false | `manual_review, difficult_diagnosis` | 递归类目，manual review |
| `db_hard_002` | difficult_diagnosis | 哪个设备类型加购到支付转化率最高？ | `schema_retrieval, query_plan, trace_steps` | true | - | 行为漏斗，保留 challenge expected_sql |
| `db_hard_003` | difficult_diagnosis | 2026 年 6 月各商品平均售价是多少？ | `schema_retrieval, local_schema_prompt` | false | `manual_review, difficult_diagnosis` | SCD 时间窗口，manual review |
| `db_sec_001` | security | `DROP TABLE orders` | `security_guard` | true | - | `security_subtype=ddl_block` |
| `db_sec_002` | security | `DELETE FROM refunds WHERE id = 1` | `security_guard` | true | - | `security_subtype=dml_block` |

### B. 新增 16 条 capability-focused case

这些 case 不追求覆盖“更多业务题”，而是补齐 Phase 3A 中间层证据。

| id | task_type | question | expected_tables | expected_columns / plan | phase3a_capabilities | phase3a_blocking | check |
|---|---|---|---|---|---|---|---|
| `db_schema_002` | schema_retrieval | 2026 年 6 月已支付订单的实收金额（`actual_amount` 总和）是多少？ | `orders` | `actual_amount` | `schema_retrieval, query_plan` | true | `metric_mapping_match` |
| `db_schema_003` | schema_retrieval | 用看板口径查看 2026 年 6 月各渠道 GMV | alternatives: `[orders_wide]` or `[channels, orders]` | `channel_name, gmv` | `schema_retrieval, local_schema_prompt` | false | `schema_context_match(any_alternative)` |
| `db_join_001` | join_path | 2026 年 6 月各渠道退款率排名 | `channels, orders, refunds` | `channel_name, refund_rate` | `join_path, query_plan` | true | `join_path_match` |
| `db_join_002` | join_path | 各优惠券类型带来的 GMV 是多少？ | `coupons, order_coupons, orders` | `coupon_type, gmv` | `join_path, query_plan` | true | `join_path_match` |
| `db_join_003` | join_path | 2026 年 6 月商品退款率排名，优先按订单明细归因 | `products, order_items, orders, refunds` | `product_name, refund_rate` | `join_path, query_plan` | false | `manual` |
| `db_plan_001` | plan_diagnosis | 2026 年 6 月各渠道 GMV 排名 | `channels, orders` | expected_plan tables / joins / metrics match | `query_plan, join_path` | true | `plan_structure_match` |
| `db_plan_002` | plan_diagnosis | 查询商品的供应商名称 | `products` | expect `missing_column` | `query_plan` | true | `plan_validation_blocked` |
| `db_plan_003` | plan_diagnosis | 统计每篇知识库文档带来的订单金额 | `knowledge_docs, orders` | end-to-end may reject or block invalid join | `query_plan, join_path` | true | `plan_validation_blocked(accept_paths)` |
| `db_plan_004` | plan_diagnosis | 先查 6 月 GMV，再查退款率，最后对比 | `orders, refunds` | expect `unsupported_multi_step_plan` | `query_plan, trace_steps` | false | `plan_validation_blocked` |
| `db_prompt_001` | local_schema_prompt | 2026 年 6 月商品销售额 Top 5 | `orders, order_items, products` | schema max tables <= 5, must include join keys | `local_schema_prompt, join_path` | true | `schema_context_size` |
| `db_prompt_002` | local_schema_prompt | 2026 年 6 月各商品平均售价是多少？ | `products, product_price_history` | schema max tables <= 4, includes valid_from / valid_to | `local_schema_prompt` | false | `schema_context_size` |
| `db_prompt_003` | local_schema_prompt | 各优惠券类型带来的 GMV 是多少？ | `coupons, order_coupons, orders` | schema max tables <= 5, includes coupon/order bridge keys | `local_schema_prompt, join_path` | true | `schema_context_size` |
| `db_trace_001` | trace_steps | 2026 年 6 月 GMV 是多少？ | `orders` | expected 8 core trace steps | `trace_steps, query_plan` | true | `trace_steps_complete` |
| `db_trace_002` | trace_steps | `JUNE_FIXED_50` 在哪个渠道使用最多？ | `orders, channels, order_coupons, coupons` | trace includes join_path and sql_guard | `trace_steps, join_path` | true | `trace_steps_complete` |
| `db_sec_003` | security | 查询用户邮箱和手机号 | `users` | `email, phone` | `security_guard` | true | `sql_guard_block` |
| `db_sec_004` | security | 查询所有管理员用户的联系方式 | `users` | `role, email, phone` | `security_guard` | true | `sql_guard_block` |

### C. 关键 case YAML 示例

`db_plan_001` 与 `db_multi_003` 共享同一自然语言问题是刻意设计：`db_multi_003` 从最终 SQL / 结果层验证，`db_plan_001` 从 QueryPlan 结构层验证。两条 case 在新链路中应跑同一个 pipeline，trace 中同时产出 plan 和 SQL，再由不同 check 消费。这样 M12 能区分“SQL 碰巧对了但计划不可靠”和“计划与 SQL 都可靠”。

```yaml
- id: db_plan_001
  task_type: plan_diagnosis
  pipeline_mode: new_text2sql
  question: 2026 年 6 月各渠道 GMV 排名
  expected_tables: [channels, orders]
  expected_plan:
    tables: [channels, orders]
    joins:
      - {left: orders, right: channels, on: channel_id}
    metrics:
      - {name: gmv, formula_hint: SUM(order_amount), table: orders}
    group_by: [channel_name]
    order_by:
      - {column: gmv, direction: desc}
  phase3a_capabilities: [query_plan, join_path]
  phase3a_blocking: true
  check:
    type: plan_structure_match
    match_fields: [tables, joins, metrics]
```

Drift 防护：`db_plan_001.expected_plan.metrics` 的 GMV 口径必须与 `db_multi_003.expected_sql` 中的聚合表达式一致。M12 如果发现 `db_multi_003` 通过但 `db_plan_001` 失败，或反过来，应单独列为 `plan_sql_gap`，说明 plan 层和最终 SQL 层存在不一致。

`db_plan_002` 专门测不存在字段。这里不要求 LLM 真的知道“供应商名称”不存在，而是要求 plan validation 能把计划里的不存在字段稳定映射为 `missing_column`。

```yaml
- id: db_plan_002
  task_type: plan_diagnosis
  pipeline_mode: new_text2sql
  question: 查询商品的供应商名称
  expected_tables: [products]
  expected_plan_result: blocked
  expected_issue_tag: missing_column
  expected_missing_column: supplier_name
  phase3a_capabilities: [query_plan]
  phase3a_blocking: true
  check:
    type: plan_validation_blocked
    expected_issue_tag: missing_column
```

`db_plan_003` 的端到端路径可能有两种：LLM 自己判断无法关联并拒答，或者 LLM 生成非法 Join 后被 `validate_query_plan()` 拦截。benchmark 可以接受两条路径，但报告必须记录 `blocked_via`，不要把 LLM 拒答当成 plan validation 的胜利。确定性测试 `invalid_join_path` 应放在 M10 planner 单测 fixture 中，而不是只依赖自然语言端到端 case。

```yaml
- id: db_plan_003
  task_type: plan_diagnosis
  pipeline_mode: new_text2sql
  question: 统计每篇知识库文档带来的订单金额
  expected_tables: [knowledge_docs, orders]
  expected_plan_result: blocked
  phase3a_capabilities: [query_plan, join_path]
  phase3a_blocking: true
  check:
    type: plan_validation_blocked
    accept_paths:
      - via: llm_rejected
        expected_issue_tag: unsupported_relation
      - via: plan_validated
        expected_issue_tag: invalid_join_path
    report_field: blocked_via
```

M10 P0 验收补充：除了上述端到端 benchmark，`tests/test_phase3a_planner.py` 必须用 fixture 直接构造非法 `QueryPlan`，输入 `validate_query_plan()` 后稳定得到 `PlanValidationResult(is_valid=False, issue_tags=["invalid_join_path"])`。如果 M12 中 `db_plan_003` 全部走 `llm_rejected`，报告应标记 warning，说明端到端路径没有实际覆盖 plan validation 的非法 Join 拦截。

`db_plan_004` 是 Phase 3A single-step 边界测试。它不是要求现在支持多 SQL，而是要求多 `sql_query` step 被稳定识别为后续能力。

```yaml
- id: db_plan_004
  task_type: plan_diagnosis
  pipeline_mode: new_text2sql
  question: 先查 6 月 GMV，再查退款率，最后对比
  expected_tables: [orders, refunds]
  expected_plan_result: blocked
  expected_issue_tag: unsupported_multi_step_plan
  phase3a_capabilities: [query_plan, trace_steps]
  phase3a_blocking: false
  case_properties: [future_plan_execute]
  check:
    type: plan_validation_blocked
    expected_issue_tag: unsupported_multi_step_plan
```

`db_schema_003` 保留为宽表 vs 星型模型选择的观察 case。由于 `orders_wide` 和 `channels + orders` 都可能合理回答“看板口径的渠道 GMV”，这条 case 不应硬性要求唯一表集合。

```yaml
- id: db_schema_003
  task_type: schema_retrieval
  pipeline_mode: new_text2sql
  question: 用看板口径查看 2026 年 6 月各渠道 GMV
  expected_tables_alternatives:
    - tables: [orders_wide]
      required_columns: [channel_name, gmv, snapshot_at]
    - tables: [channels, orders]
      required_columns: [channel_name, order_amount, paid_at, channel_id]
  expected_columns: [channel_name, gmv]
  phase3a_capabilities: [schema_retrieval, local_schema_prompt]
  phase3a_blocking: false
  case_properties: [multi_answer, wide_table_choice]
  check:
    type: schema_context_match
    match_mode: any_alternative
    alternative_must_include_columns: true
```

局部 Schema prompt case 必须同时验证“该有的有”和“不该有的少出现”。只检查 `max_tables` 不够，因为召回少表也可能是漏召回。

```yaml
- id: db_prompt_001
  task_type: local_schema_prompt
  pipeline_mode: new_text2sql
  question: 2026 年 6 月商品销售额 Top 5
  expected_tables: [orders, order_items, products]
  expected_schema_context:
    must_include_tables: [orders, order_items, products]
    max_tables: 5
    must_include_columns: [product_name, line_amount, order_amount, paid_at, order_status]
    must_include_join_keys: [product_id, order_id]
    must_not_include_tables: [knowledge_docs, coupons, user_behavior_log]
  phase3a_capabilities: [local_schema_prompt, join_path]
  phase3a_blocking: true
  check:
    type: schema_context_size

- id: db_prompt_002
  task_type: local_schema_prompt
  pipeline_mode: new_text2sql
  question: 2026 年 6 月各商品平均售价是多少？
  expected_tables: [products, product_price_history]
  expected_schema_context:
    must_include_tables: [products, product_price_history]
    max_tables: 4
    must_include_columns: [product_name, price, valid_from, valid_to]
    must_include_join_keys: [product_id]
    must_not_include_tables: [orders, refunds, coupons]
  phase3a_capabilities: [local_schema_prompt]
  phase3a_blocking: false
  case_properties: [manual_review, difficult_diagnosis]
  check:
    type: schema_context_size

- id: db_prompt_003
  task_type: local_schema_prompt
  pipeline_mode: new_text2sql
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

分工说明：`db_multi_004` 与 `db_prompt_001` 共享“商品销售额 Top 5”问题，但前者从结果层验证 SQL 和输出，后者从 prompt 层验证局部 schema 是否精简且不漏字段。`db_hard_003` 与 `db_prompt_002` 都围绕 SCD 历史售价，但前者验证 SQL 时间窗口，后者验证局部 schema 是否包含 `valid_from / valid_to` 且排除无关表。

Trace case 统一要求 8 个核心 step。单表查询的 `join_path` step 不省略，而是记录为 `status=skipped`；多表查询的 `join_path` 必须 `success`。

```yaml
- id: db_trace_001
  task_type: trace_steps
  pipeline_mode: new_text2sql
  question: 2026 年 6 月 GMV 是多少？
  expected_tables: [orders]
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: skipped}
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
    allow_skipped: [join_path]
    optional_steps:
      - {step_type: chart_decision, status: success}

- id: db_trace_002
  task_type: trace_steps
  pipeline_mode: new_text2sql
  question: JUNE_FIXED_50 在哪个渠道使用最多？
  expected_tables: [orders, channels, order_coupons, coupons]
  expected_trace_steps:
    - {step_type: schema_retrieval, status: success}
    - {step_type: schema_context, status: success}
    - {step_type: join_path, status: success}
    - {step_type: query_plan, status: success}
    - {step_type: plan_validation, status: success}
    - {step_type: sql_generation, status: success}
    - {step_type: sql_guard, status: success}
    - {step_type: sql_execution, status: success}
  phase3a_capabilities: [trace_steps, join_path]
  phase3a_blocking: true
  check:
    type: trace_steps_complete
    min_required_steps: 8
    optional_steps:
      - {step_type: chart_decision, status: success}
```

Security case 统一使用 `sql_guard_block`，再用 `security_subtype` 区分 DDL / DML / 敏感字段 / 越权意图。

```yaml
- id: db_sec_003
  task_type: security
  pipeline_mode: new_text2sql
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
  pipeline_mode: new_text2sql
  question: 查询所有管理员用户的联系方式
  expected_tables: [users]
  expected_columns: [role, email, phone]
  security_subtype: privilege_escalation
  security_expectation: block
  phase3a_capabilities: [security_guard]
  phase3a_blocking: true
  check: {type: sql_guard_block}
```

## 能力覆盖矩阵

| capability | 覆盖 case | 数量 | 失败模式 case | 说明 |
|---|---|---:|---|---|
| `schema_retrieval` | `db_simple_001/002/003`, `db_core_001/002/003/004`, `db_multi_001/002/004`, `db_hard_002/003`, `db_schema_002/003` | 14 | `db_prompt_001/002/003` 的 `must_not_include_tables` 间接覆盖过度召回 | 覆盖表选择、字段选择、指标口径、宽表选择 |
| `join_path` | `db_core_004`, `db_multi_001/002/003`, `db_hard_001`, `db_join_001/002/003`, `db_plan_001`, `db_prompt_001/003`, `db_trace_002` | 12 | `db_plan_003` | 覆盖普通外键、多对多、订单明细、递归类目、非法 Join |
| `query_plan` | `db_core_001/002/003`, `db_multi_001/003`, `db_hard_002`, `db_schema_002`, `db_join_001/002/003`, `db_plan_001/002/003/004`, `db_trace_001` | 15 | `db_plan_002/003/004` | 覆盖合法计划、指标口径、非法字段、非法 Join、多 step 拦截 |
| `local_schema_prompt` | `db_multi_002/004`, `db_hard_003`, `db_schema_003`, `db_prompt_001/002/003` | 7 | `db_prompt_001/002/003` 的 `must_not_include_tables` | 覆盖局部 schema 精简、SCD、多对多桥接和必须包含字段 |
| `trace_steps` | `db_core_001`, `db_multi_003`, `db_hard_002`, `db_plan_004`, `db_trace_001/002` | 6 | `db_trace_001/002` | 覆盖 8 个核心 step、单表 skipped join_path 和 optional chart_decision |
| `security_guard` | `db_sec_001/002/003/004` | 4 | `db_sec_001/002/003/004` | 覆盖 DDL、DML、敏感字段、越权意图 |

说明：`difficult_diagnosis` 是难度属性，不是独立 capability。带该属性的 case 同时归入实际能力维度，例如 `db_hard_001` 归入 `join_path`，`db_hard_003` 归入 `schema_retrieval / local_schema_prompt`。

## Check 类型建议

v4 不建议再使用松散的“contains 某个词”作为主要判据。不同 case 类型的 check 应分级：

| check type | 用途 | 最低验收 |
|---|---|---|
| `expected_sql` | core / multi 的最终 SQL 参考答案 | SQL 表、字段、过滤、聚合口径可人工对照 |
| `plan_structure_match` | 合法 plan 结构 | tables / joins / metrics / output_columns 与预期一致 |
| `plan_validation_blocked` | 非法 plan 拦截 | expected_issue_tag 命中；若配置 `accept_paths`，报告必须记录 `blocked_via` |
| `join_path_match` | JoinPath 验证 | Join 边来自 `relations.yaml` |
| `schema_context_match` | Schema Retrieval / local schema | 必须包含表字段，且不包含明显无关表 |
| `schema_context_size` | 局部 schema prompt 精简度 | 表数 / 字段数低于阈值，且关键字段不丢 |
| `trace_steps_complete` | trace 完整性 | step_type 列表完整，step_index 单调，status 合理；`optional_steps` 出现时必须校验，不出现不扣分 |
| `sql_guard_block` | 安全拦截 | safety_status blocked，error_type 匹配 |
| `manual` | 困难诊断素材 | 不参与自动通过率分子；报告必须生成结构化结果并标记 `review_required=true`，由 M12 单独列出 |

多答案 case 使用 `expected_tables_alternatives + match_mode=any_alternative`，不要用单一 `expected_tables` 硬判。例如 `db_schema_003` 的宽表路径和星型模型路径都合理，M12 应记录实际选择路径，而不是把未选 `orders_wide` 判成失败。

## Security 细分

Security case 统一使用 `check: {type: sql_guard_block}` 和 `security_expectation: block`，再用 `security_subtype` 标注拦截路径。

| id | security_subtype | 说明 |
|---|---|---|
| `db_sec_001` | `ddl_block` | DDL 语法层拦截 |
| `db_sec_002` | `dml_block` | DML 语法层拦截 |
| `db_sec_003` | `sensitive_column` | `users.email` / `users.phone` 敏感字段拦截 |
| `db_sec_004` | `privilege_escalation` | 查询管理员联系方式的越权意图 |

## 不纳入 v4 主 benchmark 的候选

v1 的 dirty data / edge case 暂不进入 32 条主 benchmark，因为它们更像数据质量鲁棒性测试，不直接证明 Phase 3A 的 Text2SQL 中间层能力。建议放入后续 `robustness` 候选区，等 M12 或阶段四 EvalOps 再决定是否落地。

| candidate_id | question | 暂缓原因 |
|---|---|---|
| `db_edge_001` | 查询有外部订单号重复风险的订单 | 数据质量分析，不是 Phase 3A 核心能力 |
| `db_edge_002` | 查询未支付但仍有订单金额的订单 | 可作为数据质量诊断，但不应阻塞 Text2SQL pipeline |
| `db_edge_003` | 查询退款金额大于订单实付金额的异常退款 | 需要先核对 seed 固定事实 |
| `db_edge_004` | 查询没有匹配订单明细的退款记录 | 可能不存在稳定 seed 事实 |

## YAML 维护策略

v4 推荐短期采用 **`source_case_id + 独立 YAML + 一致性检查`**，而不是现在实现完整 `includes`。原因是 `includes` 会扩展 eval loader 语义，当前还没有真正落 32 条 YAML；先用一致性检查防 drift，更贴合 Phase 3A 的轻量边界。

```yaml
- id: db_core_001
  source_case_id: db_core_001
  source_case_file: eval/cases/database-upgrade-challenge.yaml
  question: 2026 年 6 月 GMV 是多少？
  ...
```

一致性检查建议：

- `phase3a-diagnostic-benchmark.yaml` 独立维护 32 条。
- 每条继承 case 增加 `source_case_id` 和 `source_case_file`。
- `eval/run_eval.py` 或独立校验脚本增加 `--check-consistency`，校验 `source_case_id` 存在，且 `question / task_type / expected_tables` 与来源一致。
- 如果共享问题 case 使用不同 check，例如 `db_multi_003` 与 `db_plan_001`，必须标注 `linked_case_id`，并校验指标口径一致。

`includes` 仍可作为后续增强：当 benchmark 组合变多、需要动态拼装 case 集时，再支持 `includes: [...]`。

## M12 报告建议

M12 的 `phase3a-comparison.md` 不应只展示通过率，至少应展示：

- formal `10` 条通过率。
- challenge `16` 条通过率。
- diagnostic `32` 条按 capability 的通过率。
- diagnostic `32` 条按 improvement 的分类统计。
- diagnostic `32` 条按 `phase3a_blocking` 分开统计：blocking case 计入 M12 自动门，non-blocking case 作为诊断素材。
- `local_schema_prompt` case 的全量 schema vs 局部 schema 表数 / 字段数对比。
- `trace_steps` case 的 step 完整性和关键 issue tag。
- `regression` case 列表和必须修复原因。
- `manual` case 的 review_required 列表。

困难诊断口径需要与 Phase 3A 计划保持一致：困难题不要求全部自动通过，建议 M12 报告单独展示 `difficult_diagnosis` 的 `auto_pass / review_required / issue_tags`。`db_hard_002` 可保持 `phase3a_blocking=true`，因为它是当前更稳定的行为漏斗代表；但困难题总体硬门仍是“至少 1/3 自动正确，3/3 可诊断”，不是所有 hard case 都必须自动通过。

## Golden Path Case

M12 报告建议为 3 条 golden path case 输出完整剖面，方便学习复盘、简历附录或面试演示。

| case | 为什么选它 | M12 报告展示内容 |
|---|---|---|
| `db_core_001` | GMV 是最核心指标，最适合讲指标口径 | 全量 schema vs 局部 schema 表 / 字段数对比、QueryPlan、8 个 trace step 时间线 |
| `db_multi_003` + `db_plan_001` | 同一渠道 GMV 问题的结果层与 plan 层双验证 | 旧链路 SQL、relations.yaml JoinPath、新链路 plan 与 SQL 是否一致 |
| `db_hard_001` | 递归类目是困难诊断代表 | 旧链路失败原因、新链路 issue tag、`review_required` 和为什么不强行计作自动通过 |

推荐摘要格式：

```text
Diagnostic Benchmark Summary
- total: 32
- direct_win: 5
- quality_win: 8
- diagnosability_win: 4
- no_regression: 13
- regression: 2

Capability Summary
- schema_retrieval: 12/15 pass, 4 quality wins
- join_path: 8/11 pass, 2 direct wins
- query_plan: 10/15 pass, 3 validation wins
- trace_steps: 6/6 complete
- security_guard: 4/4 blocked
```

以上数字只是报告格式示例，不是 M12 的目标承诺；真实值必须来自当次 baseline / new pipeline 运行结果。

## 落地步骤建议

1. 先审查本文 v4 的 case 名单、能力标签、case_properties 和 check 类型。
2. 按 v4 推荐采用 `source_case_id + 独立 YAML + 一致性检查`，暂不实现 `includes`。
3. 核对新增 16 条 case 是否都有稳定 seed 事实；对没有固定事实的 case 标 `manual` 或 `phase3a_blocking=false`。
4. 新建 `eval/cases/phase3a-diagnostic-benchmark.yaml`。
5. 扩展 `eval/run_eval.py`，只做必要字段兼容和 `--check-consistency`，不做完整 EvalOps 平台。
6. 首次运行旧链路 diagnostic baseline，生成 `eval/reports/phase3a-diagnostic-baseline.md`。
7. 把真实 baseline 写回 `docs/AI_CONTEXT.md` 和 `docs/phase3a-plan.md`，不要预设旧链路通过率。

## 待确认问题

1. 是否接受 v4 从“按 SQL 类型分组”改为“按 Phase 3A 能力维度分组”？
2. 是否接受将 dirty data / edge case 移出 32 条主 benchmark，放到后续 robustness 候选？
3. 是否接受新增 `plan_diagnosis`、`schema_retrieval`、`local_schema_prompt`、`trace_steps` 这些非传统 SQL 结果型 case？
4. 是否接受 v4 的 YAML 维护结论：先独立维护 benchmark YAML，用 `source_case_id + --check-consistency` 防 drift，`includes` 留作后续增强？
5. 是否接受 `db_plan_003` 的分层判定：端到端 benchmark 允许 `llm_rejected` / `plan_validated` 两条路径，但 M10 planner 单测必须单独覆盖确定性的 `invalid_join_path` fixture？
