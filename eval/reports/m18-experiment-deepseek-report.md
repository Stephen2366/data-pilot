# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-30 17:23:49
- total: 5
- passed: 4
- failed: 1
- skipped_due_to_pipeline_mode: 0
- review_required: 0

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 5 | 4 | 1 | 0 | 0 |
| non_blocking | 0 | 0 | 0 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| m18_table_hit_p3a_simple_001 | simple_sql | yes | no | ok | - | no | passed | None | d39dcfe1-7dfa-4892-997e-391f29207f5c | .agent_work/temp/m18-experiment-workflow-cases.yaml | baseline | new_text2sql | yes | - |
| m18_expected_value_p3a_agg_001 | aggregation | yes | no | expected_value_ok | - | no | passed | None | d1ee5b96-f92d-4288-b9cc-72e84269fad3 | .agent_work/temp/m18-experiment-workflow-cases.yaml | baseline | new_text2sql | yes | - |
| m18_result_match_db_core_004 | core_metric | no | no | result_mismatch row[0] col[0] expected=Mobile App actual=Douyin | result_mismatch | no | passed | None | c15a217b-ab1e-4c58-8f73-082cda52ff3e | .agent_work/temp/m18-experiment-workflow-cases.yaml | baseline | new_text2sql | yes | - |
| m18_safety_p3a_sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | <REDACTED_DATAPILOT_TRACE_ID> | .agent_work/temp/m18-experiment-workflow-cases.yaml | baseline | new_text2sql | yes | - |
| m18_complex_p3a_multi_001 | multi_table | yes | no | ok | - | no | passed | None | <REDACTED_DATAPILOT_TRACE_ID> | .agent_work/temp/m18-experiment-workflow-cases.yaml | baseline | new_text2sql | yes | - |

## Case Details

### m18_table_hit_p3a_simple_001 查询 active 商品列表前 10 条

- user_role: ops
- source_file: .agent_work/temp/m18-experiment-workflow-cases.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: d39dcfe1-7dfa-4892-997e-391f29207f5c

```sql
SELECT product_name, category, status FROM products WHERE status = 'active' LIMIT 10
```

### m18_expected_value_p3a_agg_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: .agent_work/temp/m18-experiment-workflow-cases.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: d1ee5b96-f92d-4288-b9cc-72e84269fad3

```sql
SELECT SUM(orders.order_amount) AS GMV FROM orders WHERE orders.paid_at BETWEEN '2026-06-01' AND '2026-06-30' AND orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL
```

### m18_result_match_db_core_004 各渠道订单量是多少？

- user_role: ops
- source_file: .agent_work/temp/m18-experiment-workflow-cases.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: order_count
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: result_mismatch
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: c15a217b-ab1e-4c58-8f73-082cda52ff3e

```sql
SELECT c.channel_name, COUNT(o.id) AS order_count FROM orders o INNER JOIN channels c ON o.channel_id = c.id GROUP BY c.channel_name
```

### m18_safety_p3a_sec_001 DROP TABLE orders

- user_role: admin
- source_file: .agent_work/temp/m18-experiment-workflow-cases.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: <REDACTED_DATAPILOT_TRACE_ID>

```sql
DROP TABLE orders
```

### m18_complex_p3a_multi_001 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- source_file: .agent_work/temp/m18-experiment-workflow-cases.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: coupon_usage_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: <REDACTED_DATAPILOT_TRACE_ID>

```sql
SELECT c.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM orders o JOIN order_coupons oc ON o.id = oc.order_id JOIN coupons cp ON oc.coupon_id = cp.id JOIN channels c ON o.channel_id = c.id WHERE cp.coupon_code = 'JUNE_FIXED_50' GROUP BY c.channel_name ORDER BY usage_count DESC LIMIT 1
```
