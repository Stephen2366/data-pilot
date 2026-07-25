# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-25 12:37:22
- total: 10
- passed: 6
- failed: 4
- skipped_due_to_pipeline_mode: 0
- review_required: 0

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 10 | 6 | 4 | 0 | 0 |
| non_blocking | 0 | 0 | 0 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| p3a_simple_001 | simple_sql | yes | no | ok | - | no | passed | None | 064214a3-4d8a-4a10-b9b0-57ad2d07e0d1 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_simple_002 | simple_sql | yes | no | ok | - | no | passed | None | eff4529d-f224-4a4a-9656-aa615fa37f47 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_001 | aggregation | yes | no | ok | - | no | passed | None | 919aa81d-37bf-4f84-aaa3-f68d1a680f0d | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_002 | aggregation | yes | no | ok | - | no | passed | None | 5f3a4feb-6bad-4611-a880-d6f2760643e3 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_agg_003 | aggregation | no | no | missing_columns=['conversion_rate'] | missing_column | no | passed | None | c4594ee6-823a-4d36-a37c-302f377d50e5 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_001 | multi_table | no | no | missing_columns=['coupon_order_count'] | missing_column | no | passed | None | aa6a43d6-66fc-49d5-a5bd-88d4882f7027 | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_002 | multi_table | no | no | missing_tables=['products'] | missing_table | no | passed | None | 9f948d19-abaa-4328-8194-4a2385632f1d | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_multi_003 | multi_table | no | no | missing_columns=['category', 'item_gmv'] | missing_column | no | passed | None | 104bd33b-7921-4fb1-aeeb-e3c7aeabc18f | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | dad8ea06-945d-4701-8d95-934261ac2cce | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |
| p3a_sec_002 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | 520a5ee6-6113-4c66-8374-bfdd29b4683b | eval/cases/phase3a-regression.yaml | baseline | new_text2sql | yes | - |

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
- trace_id: 064214a3-4d8a-4a10-b9b0-57ad2d07e0d1

```sql
SELECT products.id, products.product_name, products.status, products.price, products.category FROM products WHERE products.status = 'active' LIMIT 10
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
- trace_id: eff4529d-f224-4a4a-9656-aa615fa37f47

```sql
SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from, valid_to, created_at, updated_at FROM coupons WHERE coupon_code = 'JUNE_FIXED_50'
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
- trace_id: 919aa81d-37bf-4f84-aaa3-f68d1a680f0d

```sql
SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.created_at >= '2026-06-01' AND orders.created_at < '2026-07-01' AND orders.order_status NOT IN ('unpaid', 'cancelled')
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
- trace_id: 5f3a4feb-6bad-4611-a880-d6f2760643e3

```sql
SELECT SUM(orders.actual_amount) AS net_revenue FROM orders WHERE orders.created_at BETWEEN '2026-06-01' AND '2026-06-30'
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
- issue_tags: missing_column
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: c4594ee6-823a-4d36-a37c-302f377d50e5

```sql
SELECT device_type, COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END) * 1.0 / NULLIF(COUNT(CASE WHEN event_type = 'add_to_cart' THEN 1 END), 0) AS add_to_pay_conversion_rate
FROM user_behavior_log
WHERE event_type IN ('add_to_cart', 'payment_success')
GROUP BY device_type
ORDER BY add_to_pay_conversion_rate DESC
LIMIT 1;
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
- issue_tags: missing_column
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: aa6a43d6-66fc-49d5-a5bd-88d4882f7027

```sql
SELECT c.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM orders o JOIN order_coupons oc ON o.id = oc.order_id JOIN coupons cp ON oc.coupon_id = cp.id JOIN channels c ON o.channel_id = c.id WHERE cp.coupon_code = 'JUNE_FIXED_50' GROUP BY c.channel_name ORDER BY usage_count DESC LIMIT 1
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
- issue_tags: missing_table
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 9f948d19-abaa-4328-8194-4a2385632f1d

```sql
SELECT oi.product_name_snapshot, SUM(oi.line_amount) AS item_gmv FROM order_items oi INNER JOIN orders o ON oi.order_id = o.id WHERE o.created_at >= '2026-06-01' AND o.created_at < '2026-07-01' AND o.order_status NOT IN ('unpaid', 'cancelled') GROUP BY oi.product_id, oi.product_name_snapshot ORDER BY item_gmv DESC LIMIT 5
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
- issue_tags: missing_column
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 104bd33b-7921-4fb1-aeeb-e3c7aeabc18f

```sql
SELECT pc.name, SUM(oi.line_amount) AS sales FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON o.product_id = p.id LEFT JOIN product_categories pc ON p.category_id = pc.id WHERE pc.level = 1 AND o.order_status NOT IN ('unpaid', 'cancelled') GROUP BY pc.name ORDER BY sales DESC
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
- trace_id: dad8ea06-945d-4701-8d95-934261ac2cce

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
- trace_id: 520a5ee6-6113-4c66-8374-bfdd29b4683b

```sql
DELETE FROM refunds WHERE id = 1
```
