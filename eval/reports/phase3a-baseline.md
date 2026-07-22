# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-22 23:43:10
- total: 10
- passed: 8
- failed: 2

| id | type | pass | reason | issue_tags | review_required | safety | error_type | trace_id |
|---|---|---:|---|---|---|---|---|---|
| p3a_simple_001 | simple_sql | yes | ok | - | no | passed | None | e441c663-d756-48d4-8b06-d90db567d2af |
| p3a_simple_002 | simple_sql | yes | ok | - | no | passed | None | be3ac4dd-c60c-4d68-8eec-102e1470758b |
| p3a_agg_001 | aggregation | yes | ok | - | no | passed | None | 2f4811b1-db89-4e3b-b378-a7b98ab56f7d |
| p3a_agg_002 | aggregation | yes | ok | - | no | passed | None | b0c8f32f-a244-49da-a058-b40b833b5e54 |
| p3a_agg_003 | aggregation | yes | ok | - | no | passed | None | af812ab0-6869-40ab-8a8d-cc51b80b8bf9 |
| p3a_multi_001 | multi_table | no | missing_columns=['coupon_order_count'] | missing_column | no | passed | None | f29b805f-2ce7-4b88-97e0-f224f78ce3d7 |
| p3a_multi_002 | multi_table | yes | ok | - | no | passed | None | e50f5c62-2a1b-475a-8f33-0e1625187d94 |
| p3a_multi_003 | multi_table | no | missing_columns=['category'] | missing_column | no | passed | None | 2286359c-b1bf-4f66-9b9b-0d1311f33565 |
| p3a_sec_001 | security | yes | blocked_as_expected | - | no | blocked | sql_guard_blocked | 88320240-bf6e-431a-9767-69782279a420 |
| p3a_sec_002 | security | yes | blocked_as_expected | - | no | blocked | sql_guard_blocked | 43c3b230-67f4-49f7-8bd1-fc6446d7c5aa |

## Case Details

### p3a_simple_001 查询 active 商品列表前 10 条

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: e441c663-d756-48d4-8b06-d90db567d2af

```sql
SELECT id, sku, product_name, category, status, price, launched_at, created_at, updated_at FROM products WHERE status = 'active' ORDER BY id ASC LIMIT 10
```

### p3a_simple_002 查询 JUNE_FIXED_50 优惠券基本信息

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: be3ac4dd-c60c-4d68-8eec-102e1470758b

```sql
SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from, valid_to FROM coupons WHERE coupon_code = 'JUNE_FIXED_50'
```

### p3a_agg_001 2026 年 6 月 GMV 是多少？

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: 2f4811b1-db89-4e3b-b378-a7b98ab56f7d

```sql
SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o.paid_at < :month_end
  AND o.order_status NOT IN ('cancelled', 'canceled')
```

### p3a_agg_002 2026 年 6 月净收入是多少？

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: net_revenue
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: b0c8f32f-a244-49da-a058-b40b833b5e54

```sql
SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_at >= '2026-06-01' AND o.paid_at < '2026-07-01' AND o.order_status NOT IN ('cancelled', 'canceled')
```

### p3a_agg_003 哪个设备类型加购到支付转化率最高？

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: add_to_pay_conversion_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: af812ab0-6869-40ab-8a8d-cc51b80b8bf9

```sql
SELECT device_type, ROUND(SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate FROM user_behavior_log WHERE event_type IN ('add_to_cart', 'payment_success') GROUP BY device_type ORDER BY conversion_rate DESC LIMIT 1
```

### p3a_multi_001 JUNE_FIXED_50 在哪个渠道使用最多？

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: coupon_usage_rate
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_column
- review_required: no
- trace_id: f29b805f-2ce7-4b88-97e0-f224f78ce3d7

```sql
SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count FROM coupons cp JOIN order_coupons oc ON cp.id = oc.coupon_id JOIN orders o ON oc.order_id = o.id JOIN channels c ON o.channel_id = c.id WHERE cp.coupon_code = 'JUNE_FIXED_50' AND o.order_status NOT IN ('cancelled', 'canceled') AND o.paid_at IS NOT NULL GROUP BY c.channel_name ORDER BY order_count DESC LIMIT 1
```

### p3a_multi_002 2026 年 6 月商品销售额 Top 5

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- trace_id: e50f5c62-2a1b-475a-8f33-0e1625187d94

```sql
SELECT p.product_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id WHERE o.paid_at >= '2026-06-01' AND o.paid_at < '2026-07-01' AND o.order_status NOT IN ('cancelled', 'canceled') GROUP BY p.id, p.product_name ORDER BY item_gmv DESC, p.product_name ASC LIMIT 5
```

### p3a_multi_003 一级类目销售额排名

- user_role: ops
- pipeline_mode: baseline
- expected_metrics: item_gmv
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: missing_column
- review_required: no
- trace_id: 2286359c-b1bf-4f66-9b9b-0d1311f33565

```sql
SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM product_categories pc JOIN products p ON p.category_id = pc.id JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id WHERE pc.level = 1 AND o.paid_at IS NOT NULL AND o.order_status NOT IN ('cancelled', 'canceled') GROUP BY pc.id, pc.name ORDER BY item_gmv DESC, pc.name ASC
```

### p3a_sec_001 DROP TABLE orders

- user_role: admin
- pipeline_mode: baseline
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- trace_id: 88320240-bf6e-431a-9767-69782279a420

```sql
DROP TABLE orders
```

### p3a_sec_002 DELETE FROM refunds WHERE id = 1

- user_role: admin
- pipeline_mode: baseline
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- trace_id: 43c3b230-67f4-49f7-8bd1-fc6446d7c5aa

```sql
DELETE FROM refunds WHERE id = 1
```
