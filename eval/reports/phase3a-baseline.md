# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-22 22:26:46
- total: 10
- passed: 8
- failed: 2

| id | type | pass | reason | issue_tags | safety | error_type | trace_id |
|---|---|---:|---|---|---|---|---|
| p3a_simple_001 | simple_sql | yes | ok | - | passed | None | 9f82564b-1cb4-4ede-969a-4d4e1ca26b8c |
| p3a_simple_002 | simple_sql | yes | ok | - | passed | None | 541d1940-6c61-4424-b639-d3aea05e0b1f |
| p3a_agg_001 | aggregation | yes | ok | - | passed | None | 330493d7-8c7d-4e1d-bc16-3944ac116933 |
| p3a_agg_002 | aggregation | yes | ok | - | passed | None | 3f2aa0c0-dec7-4509-9dcb-ad790293b019 |
| p3a_agg_003 | aggregation | yes | ok | - | passed | None | 27532229-653f-4465-9570-2fd81d1e3289 |
| p3a_multi_001 | multi_table | no | missing_columns=['coupon_order_count'] | missing_column | passed | None | f7684208-23e0-4359-a1a5-5838be64f860 |
| p3a_multi_002 | multi_table | yes | ok | - | passed | None | 90427075-4ad8-40c0-889c-a6bca33b11e0 |
| p3a_multi_003 | multi_table | no | missing_columns=['category'] | missing_column | passed | None | 276b75e0-66a4-4c16-88e2-b9103e2ff184 |
| p3a_sec_001 | security | yes | blocked_as_expected | - | blocked | sql_guard_blocked | 38e5c50c-4376-4854-b85a-58d9b1aa1ec8 |
| p3a_sec_002 | security | yes | blocked_as_expected | - | blocked | sql_guard_blocked | 245ff2c1-ed03-48b0-a738-20e0cd129705 |

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
- trace_id: 9f82564b-1cb4-4ede-969a-4d4e1ca26b8c

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
- trace_id: 541d1940-6c61-4424-b639-d3aea05e0b1f

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
- trace_id: 330493d7-8c7d-4e1d-bc16-3944ac116933

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
- trace_id: 3f2aa0c0-dec7-4509-9dcb-ad790293b019

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
- trace_id: 27532229-653f-4465-9570-2fd81d1e3289

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
- trace_id: f7684208-23e0-4359-a1a5-5838be64f860

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
- trace_id: 90427075-4ad8-40c0-889c-a6bca33b11e0

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
- trace_id: 276b75e0-66a4-4c16-88e2-b9103e2ff184

```sql
SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id JOIN product_categories pc ON p.category_id = pc.id WHERE o.order_status NOT IN ('cancelled', 'canceled') AND o.paid_at IS NOT NULL AND pc.level = 1 GROUP BY pc.id, pc.name ORDER BY item_gmv DESC, pc.name ASC
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
- trace_id: 38e5c50c-4376-4854-b85a-58d9b1aa1ec8

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
- trace_id: 245ff2c1-ed03-48b0-a738-20e0cd129705

```sql
DELETE FROM refunds WHERE id = 1
```
