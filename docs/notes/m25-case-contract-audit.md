# M25 Case Contract Audit（2026-08-07）

## 审计范围与规则

- 范围：`phase3a-regression.yaml` 10 条、`database-upgrade-challenge.yaml` 16 条、`phase3a-diagnostic-benchmark.yaml` 16 条，共 42 raw cases。
- 合同来源只允许三类：题面显式声明、`domain_pack/metrics.yaml` / state 文档已登记的权威默认、人工/诊断项明确标记不作精确自动答案硬门。
- 精确结果题逐项核对 tables、columns、metrics、时间、过滤、排序、LIMIT、alias、reference SQL 与 check type；安全题只由 SQL Guard 判定；Context/Plan/Trace 题不冒充语义答案题。
- `semantic_group_id` 是独立问题分母事实源；`linked_case_id` 继续表达某条诊断 case 的具体链接。

## 自动结果与安全合同

| 语义组 / case | 合同来源 | 审计结果 |
|---|---|---|
| `active_products_top10` | 题面显式列、状态、排序、LIMIT | 已修订；formal/challenge 同步 |
| `june_fixed_coupon_basic_info` | 题面显式三列 | 已修订；不再依赖“基本信息”猜列 |
| `db_simple_002` | 题面显式月份、成交语义、三列、排序、LIMIT | 已修订 |
| `june_gmv` | 题面时间 + canonical `gmv` metric | 通过 |
| `db_core_002` | 题面时间/Top1/tie-break + canonical `refund_rate` | 已修订为 completed 退款去重订单分子；明细优先、整单 fallback |
| `june_net_revenue` | 题面时间 + canonical `net_revenue` metric | 通过 |
| `db_core_004` | 题面显式排序 + canonical `order_count` | 已修订 |
| `june_fixed_coupon_top_channel` | 题面 Top1/tie-break + canonical `coupon_order_count` | 已修订；不新增 `coupon_usage_count` alias |
| `june_root_category_sales` | 题面显式月份、递归子类目、排序 | 已修订；fidelity 对 CTE 保持保守 `indeterminate` |
| `june_channel_gmv_ranking` | 题面时间/排序 + canonical `gmv` | 已修订 |
| `june_product_sales_top5` | 题面时间/Top5/tie-break + canonical `item_gmv` | 已修订 |
| `top_device_conversion` | 题面 Top1/tie-break + canonical conversion metric | 已修订 |
| `unsafe_drop_orders` / `unsafe_delete_refund` / `db_sec_003` / `db_sec_004` | SQL Guard 硬规则 | 通过；不进入 semantic answer 分母 |

## 自动诊断合同

| case | check type | 审计结论 |
|---|---|---|
| `db_schema_002` | `metric_mapping_match` | 只验证 canonical metric 映射 |
| `db_schema_003` | `schema_context_match` | 只验证目标 SchemaGraph 事实存在 |
| `db_join_001/002` | `join_path_match` | 只验证关系路径，不声称最终答案正确 |
| `db_plan_001` | `plan_structure_match` | 只验证计划结构 |
| `db_plan_002/004` | `plan_validation_blocked` | 只验证已登记的不支持请求被拒绝 |
| `db_prompt_001/003` | `schema_context_size` | 只验证局部 context 边界 |
| `db_trace_001/002` | `trace_steps_complete` | 只验证 trace 完整性 |

## 人工 / 诊断项

- `db_hard_001`、`db_hard_003`、`db_join_003`、`db_plan_003`、`db_prompt_002` 保留 manual/diagnostic 身份，不进入精确自动答案硬门。
- `avg_selling_price` 已收口为“时间窗口相交的价格历史记录按记录条数算术平均”，但 `db_hard_003` 本模块仍保持 manual，不因题面写清就直接升级自动评分。
- `db_hard_001` 的递归 CTE 在 provider 没有有效响应或 fidelity 为 `indeterminate` 时，不宣称能力通过或失败。

## 分母快照

- challenge + diagnostic：32 raw cases，26 independent semantic groups，6 个额外 linked/equivalent case。
- formal + challenge + diagnostic：42 raw cases，26 independent semantic groups，16 个额外重复检查实例。
- M25 报告必须并列展示 raw/group 分母与 `semantic_answer`、`safety`、`plan_and_trace`、`provider_reliability`、`manual_or_judge`、`end_to_end` 视图；综合 automated capability 不得改名为 SQL 正确率。
