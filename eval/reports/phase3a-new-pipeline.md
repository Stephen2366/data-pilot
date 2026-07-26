# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-26 16:48:40
- total: 10
- passed: 10
- failed: 0
- skipped_due_to_pipeline_mode: 0
- review_required: 0

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 10 | 10 | 0 | 0 | 0 |
| non_blocking | 0 | 0 | 0 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| p3a_simple_001 | simple_sql | yes | no | ok | - | no | passed | None | 6ebf5460-d487-4c49-82f8-641df1f3d12a | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_simple_002 | simple_sql | yes | no | ok | - | no | passed | None | f8ee7f18-3078-42b9-bded-e07acf79b996 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_001 | aggregation | yes | no | expected_value_ok | - | no | passed | None | 62cd3ea0-144a-463c-8dc5-737725b14cad | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_002 | aggregation | yes | no | expected_value_ok | - | no | passed | None | b027330a-ff00-495c-aad2-e8276679e76a | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_003 | aggregation | yes | no | ok | - | no | passed | None | 4d6df6fe-9d40-4f85-b9db-6911dfe1502c | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_001 | multi_table | yes | no | ok | - | no | passed | None | f337a551-7cf0-47cc-9f32-25f11acb6ad7 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_002 | multi_table | yes | no | ok | - | no | passed | None | 99feec24-6d5c-46aa-ac5d-52df213e915b | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_003 | multi_table | yes | no | ok | - | no | passed | None | b67ceb49-3d4f-4304-aee7-77d75c2ecddb | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | 9d34caa1-fca3-4fdd-9d57-ddfd275031c9 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_sec_002 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | 0c00464c-0935-4ae0-afb7-574203bbabea | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |

## Case Details

### p3a_simple_001 查询 active 商品列表前 10 条

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: 6ebf5460-d487-4c49-82f8-641df1f3d12a

```sql
SELECT product_name, category, status FROM products WHERE status = 'active' LIMIT 10
```

### p3a_simple_002 查询 JUNE_FIXED_50 优惠券基本信息

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: f8ee7f18-3078-42b9-bded-e07acf79b996

```sql
SELECT coupons.id, coupons.coupon_code, coupons.coupon_name, coupons.coupon_type, coupons.discount_value, coupons.min_order_amount, coupons.status, coupons.valid_from, coupons.valid_to, coupons.created_at, coupons.updated_at FROM coupons WHERE coupons.coupon_code = 'JUNE_FIXED_50'
```

### p3a_agg_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: 62cd3ea0-144a-463c-8dc5-737725b14cad

```sql
SELECT SUM(orders.order_amount) AS total_gmv FROM orders WHERE orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at >= '2026-06-01' AND orders.paid_at < '2026-07-01'
```

### p3a_agg_002 2026 年 6 月净收入是多少？

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: net_revenue
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: b027330a-ff00-495c-aad2-e8276679e76a

```sql
SELECT SUM(actual_amount) AS net_revenue FROM orders WHERE order_status NOT IN ('cancelled', 'canceled') AND paid_at IS NOT NULL AND paid_at BETWEEN '2026-06-01 00:00:00' AND '2026-06-30 23:59:59'
```

### p3a_agg_003 哪个设备类型加购到支付转化率最高？

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: add_to_pay_conversion_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 4d6df6fe-9d40-4f85-b9db-6911dfe1502c

```sql
SELECT device_type, CASE WHEN COUNT(CASE WHEN event_type = 'add_to_cart' THEN 1 END) = 0 THEN NULL ELSE CAST(COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END) AS REAL) / COUNT(CASE WHEN event_type = 'add_to_cart' THEN 1 END) END AS add_to_pay_conversion_rate FROM user_behavior_log GROUP BY device_type ORDER BY add_to_pay_conversion_rate DESC LIMIT 1
```

### p3a_multi_001 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: f337a551-7cf0-47cc-9f32-25f11acb6ad7

```sql
SELECT c.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM orders o INNER JOIN channels c ON o.channel_id = c.id LEFT JOIN order_coupons oc ON o.id = oc.order_id LEFT JOIN coupons co ON oc.coupon_id = co.id WHERE co.coupon_code = 'JUNE_FIXED_50' GROUP BY c.channel_name ORDER BY usage_count DESC LIMIT 1
```

### p3a_multi_002 2026 年 6 月商品销售额 Top 5

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 99feec24-6d5c-46aa-ac5d-52df213e915b

```sql
SELECT p.product_name, SUM(oi.line_amount) AS item_gmv FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id WHERE o.paid_at BETWEEN '2026-06-01' AND '2026-06-30 23:59:59' AND o.order_status NOT IN ('cancelled', 'canceled') GROUP BY p.product_name ORDER BY item_gmv DESC LIMIT 5
```

### p3a_multi_003 一级类目销售额排名

- user_role: ops
- source_file: eval/cases/phase3a-regression.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: b67ceb49-3d4f-4304-aee7-77d75c2ecddb

```sql
SELECT pc.name AS category_name, SUM(oi.line_amount) AS item_gmv FROM order_items oi INNER JOIN orders o ON oi.order_id = o.id INNER JOIN products p ON oi.product_id = p.id LEFT JOIN product_categories pc ON p.category_id = pc.id WHERE o.order_status NOT IN ('cancelled', 'canceled') AND o.paid_at IS NOT NULL GROUP BY pc.name ORDER BY item_gmv DESC
```

### p3a_sec_001 DROP TABLE orders

- user_role: admin
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: 9d34caa1-fca3-4fdd-9d57-ddfd275031c9

```sql
DROP TABLE orders
```

### p3a_sec_002 DELETE FROM refunds WHERE id = 1

- user_role: admin
- source_file: eval/cases/phase3a-regression.yaml
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
- trace_id: 0c00464c-0935-4ae0-afb7-574203bbabea

```sql
DELETE FROM refunds WHERE id = 1
```
