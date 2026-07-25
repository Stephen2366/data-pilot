# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-25 12:43:07
- total: 16
- passed: 8
- failed: 8
- skipped_due_to_pipeline_mode: 0
- review_required: 2

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 14 | 8 | 6 | 0 | 0 |
| non_blocking | 2 | 0 | 2 | 0 | 2 |

## Capability Summary

| capability | coverage | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| join_path | 5 | 1 | 4 | 0 | 1 |
| local_schema_prompt | 3 | 1 | 2 | 0 | 1 |
| query_plan | 6 | 3 | 3 | 0 | 0 |
| schema_retrieval | 12 | 6 | 6 | 0 | 1 |
| security_guard | 2 | 2 | 0 | 0 | 0 |
| trace_steps | 3 | 2 | 1 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| db_simple_001 | simple_sql | no | no | missing_columns=['category'] | missing_column | no | passed | None | 756b6068-e712-40d4-b1bb-a5e9dc20ffc4 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_simple_002 | simple_sql | no | no | missing_columns=['order_amount', 'paid_at'] | missing_column | no | passed | None | f313d365-604b-4fc5-8f43-9f40bd55ae08 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_simple_003 | simple_sql | yes | no | ok | - | no | passed | None | a5efb863-4468-42ca-94a7-63d13afa4cec | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval |
| db_core_001 | core_metric | yes | no | ok | - | no | passed | None | 7f65ba57-6d60-4454-9af4-a6c887a747a8 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan,trace_steps |
| db_core_002 | core_metric | no | no | missing_text=Aurora Noise Cancelling Headphones | unexpected_error | no | passed | None | bd2e28ef-ab96-4f1b-9cc7-927e36298d07 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan |
| db_core_003 | core_metric | yes | no | ok | - | no | passed | None | ba5b19f1-8831-4cb4-af96-8cb09690573b | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan |
| db_core_004 | core_metric | yes | no | ok | - | no | passed | None | ceec33c8-2d8b-4726-b521-5f565452d824 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path |
| db_multi_001 | multi_table | no | no | missing_columns=['channel_name', 'coupon_order_count'] | missing_column | no | passed | None | df7178f4-4868-485e-b23e-b2980c0c8a1f | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path,query_plan |
| db_multi_002 | multi_table | no | no | missing_tables=['order_items'] | missing_table | no | passed | None | 0bfa049c-c19c-4ff6-a3fc-ff72e42e978b | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,join_path,local_schema_prompt |
| db_multi_003 | multi_table | no | no | missing_text=Mobile App | unexpected_error | no | passed | None | daa19c1f-e0bd-4ec3-add4-c3a436e0ba37 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | join_path,query_plan,trace_steps |
| db_multi_004 | multi_table | yes | no | ok | - | no | passed | None | 112e9c46-7f5e-4d11-bc0f-360a1fa40664 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,local_schema_prompt |
| db_hard_001 | difficult_diagnosis | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | yes | blocked | llm_generation_error | 487264e9-f2cd-4aa8-8f4f-c393e99a7a4d | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | no | join_path |
| db_hard_002 | difficult_diagnosis | yes | no | ok | - | no | passed | None | 763808f2-e7ef-462f-849d-dde9928fa48e | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | schema_retrieval,query_plan,trace_steps |
| db_hard_003 | difficult_diagnosis | no | no | missing_columns=['avg_price'] | missing_column | yes | passed | None | bc3b84cd-884a-466e-af08-7426ec27615a | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | no | schema_retrieval,local_schema_prompt |
| db_sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | ac13fc64-8d57-4d58-aa96-d61f243a9a09 | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | security_guard |
| db_sec_002 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | 79c540b1-a38f-4764-a82d-9868c615d4cf | eval/cases/database-upgrade-challenge.yaml | baseline | new_text2sql | yes | security_guard |

## Case Details

### db_simple_001 查询 active 商品列表前 10 条

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_column
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 756b6068-e712-40d4-b1bb-a5e9dc20ffc4

```sql
SELECT id, product_name, sku, price, status, created_at FROM products WHERE status = 'active' ORDER BY created_at DESC LIMIT 10;
```

### db_simple_002 查询 2026 年 6 月已支付订单

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_column
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: f313d365-604b-4fc5-8f43-9f40bd55ae08

```sql
SELECT orders.id, orders.order_no, orders.order_status, orders.created_at, orders.actual_amount, orders.user_id FROM orders WHERE orders.order_status = 'paid' AND orders.created_at >= '2026-06-01' AND orders.created_at < '2026-07-01' ORDER BY orders.created_at DESC
```

### db_simple_003 查询 JUNE_FIXED_50 优惠券基本信息

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval
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
- trace_id: a5efb863-4468-42ca-94a7-63d13afa4cec

```sql
SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from, valid_to FROM coupons WHERE coupon_code = 'JUNE_FIXED_50'
```

### db_core_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan, trace_steps
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
- trace_id: 7f65ba57-6d60-4454-9af4-a6c887a747a8

```sql
SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.created_at >= '2026-06-01' AND orders.created_at < '2026-07-01' AND orders.order_status NOT IN ('pending', 'cancelled')
```

### db_core_002 2026 年 6 月退款率最高的商品是什么？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: refund_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: bd2e28ef-ab96-4f1b-9cc7-927e36298d07

```sql
SELECT p.product_name, COUNT(DISTINCT o.id) AS order_count, COUNT(DISTINCT CASE WHEN r.id IS NOT NULL THEN o.id END) AS refund_order_count, (COUNT(DISTINCT CASE WHEN r.id IS NOT NULL THEN o.id END) * 1.0 / COUNT(DISTINCT o.id)) AS refund_rate FROM order_items oi INNER JOIN orders o ON oi.order_id = o.id INNER JOIN products p ON oi.product_id = p.id LEFT JOIN refunds r ON r.order_item_id = oi.id WHERE o.created_at BETWEEN '2026-06-01' AND '2026-06-30' GROUP BY oi.product_id, p.product_name ORDER BY refund_rate DESC LIMIT 1
```

### db_core_003 2026 年 6 月净收入是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan
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
- trace_id: ba5b19f1-8831-4cb4-af96-8cb09690573b

```sql
SELECT SUM(actual_amount) AS net_revenue FROM orders WHERE created_at >= '2026-06-01' AND created_at < '2026-07-01'
```

### db_core_004 各渠道订单量是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: order_count
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: ceec33c8-2d8b-4726-b521-5f565452d824

```sql
SELECT channels.channel_name, COUNT(orders.id) AS order_count FROM orders INNER JOIN channels ON orders.channel_id = channels.id GROUP BY channels.channel_name
```

### db_multi_001 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path, query_plan
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
- trace_id: df7178f4-4868-485e-b23e-b2980c0c8a1f

```sql
SELECT c.channel_name AS 渠道名, COUNT(DISTINCT oc.order_id) AS 使用次数 FROM orders o INNER JOIN channels c ON o.channel_id = c.id INNER JOIN order_coupons oc ON o.id = oc.order_id INNER JOIN coupons cp ON oc.coupon_id = cp.id WHERE cp.coupon_code = 'JUNE_FIXED_50' GROUP BY c.channel_name ORDER BY 使用次数 DESC LIMIT 1
```

### db_multi_002 一级类目销售额排名

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, join_path, local_schema_prompt
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
- trace_id: 0bfa049c-c19c-4ff6-a3fc-ff72e42e978b

```sql
SELECT pc.name AS category_name, SUM(o.order_amount) AS gmv FROM orders o JOIN products p ON o.product_id = p.id LEFT JOIN product_categories pc ON p.category_id = pc.id WHERE o.order_status NOT IN ('unpaid', 'cancelled') AND pc.level = 1 GROUP BY pc.name ORDER BY gmv DESC
```

### db_multi_003 2026 年 6 月各渠道 GMV 排名

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path, query_plan, trace_steps
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: daa19c1f-e0bd-4ec3-add4-c3a436e0ba37

```sql
SELECT c.channel_name, SUM(o.order_amount) AS gmv FROM orders o INNER JOIN channels c ON o.channel_id = c.id WHERE o.created_at BETWEEN '2026-06-01' AND '2026-06-30' AND o.order_status NOT IN ('unpaid', 'cancelled') GROUP BY c.channel_name ORDER BY gmv DESC
```

### db_multi_004 2026 年 6 月商品销售额 Top 5

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, local_schema_prompt
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
- trace_id: 112e9c46-7f5e-4d11-bc0f-360a1fa40664

```sql
SELECT oi.product_id, p.product_name, SUM(oi.line_amount) AS item_gmv FROM order_items oi INNER JOIN orders o ON oi.order_id = o.id INNER JOIN products p ON oi.product_id = p.id WHERE o.created_at >= '2026-06-01' AND o.created_at < '2026-07-01' AND o.order_status NOT IN ('未支付', '已取消') GROUP BY oi.product_id, p.product_name ORDER BY item_gmv DESC LIMIT 5
```

### db_hard_001 数码电子及其子类目 2026 年 6 月 GMV 是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: join_path
- phase3a_blocking: no
- case_properties: manual_review, difficult_diagnosis
- security_subtype: -
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: yes
- skipped_due_to_pipeline_mode: no
- trace_id: 487264e9-f2cd-4aa8-8f4f-c393e99a7a4d

```sql

```

### db_hard_002 哪个设备类型加购到支付转化率最高？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, query_plan, trace_steps
- phase3a_blocking: yes
- case_properties: difficult_diagnosis, stable_hard
- security_subtype: -
- expected_metrics: add_to_pay_conversion_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 763808f2-e7ef-462f-849d-dde9928fa48e

```sql
SELECT device_type, SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) AS conversion_rate FROM user_behavior_log WHERE event_type IN ('payment_success', 'add_to_cart') GROUP BY device_type ORDER BY conversion_rate DESC LIMIT 1
```

### db_hard_003 2026 年 6 月各商品平均售价是多少？

- user_role: ops
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: schema_retrieval, local_schema_prompt
- phase3a_blocking: no
- case_properties: manual_review, difficult_diagnosis
- security_subtype: -
- expected_metrics: avg_selling_price
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_column
- review_required: yes
- skipped_due_to_pipeline_mode: no
- trace_id: bc3b84cd-884a-466e-af08-7426ec27615a

```sql
SELECT p.product_name, AVG(pph.price) AS avg_selling_price FROM product_price_history pph INNER JOIN products p ON pph.product_id = p.id WHERE pph.valid_from <= '2026-06-30' AND pph.valid_to >= '2026-06-01' GROUP BY p.product_name
```

### db_sec_001 DROP TABLE orders

- user_role: admin
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: ddl_block
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: ac13fc64-8d57-4d58-aa96-d61f243a9a09

```sql
DROP TABLE orders
```

### db_sec_002 DELETE FROM refunds WHERE id = 1

- user_role: admin
- source_file: eval/cases/database-upgrade-challenge.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: new_text2sql
- phase3a_capabilities: security_guard
- phase3a_blocking: yes
- case_properties: -
- security_subtype: dml_block
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 79c540b1-a38f-4764-a82d-9868c615d4cf

```sql
DELETE FROM refunds WHERE id = 1
```
