# Phase 3A 新旧链路对照报告

- 生成时间：2026-07-25 12:43:34
- 共同 case 数：10
- 仅在 baseline 中出现：0
- 仅在新 pipeline 中出现：0

## 1. 通过率对比

| 指标 | 旧链路 (baseline) | 新链路 (new_text2sql) | 变化 |
|---|---:|---:|---|
| passed | 8 | 8 | 0 |
| blocked | 2 | 2 | 0 |
| error | 0 | 0 | 0 |
| 通过率 | 8/10 (80%) | 8/10 (80%) | — |

## 2. Schema 精简度对比

新链路通过 M9 Schema Retrieval 只给 LLM 看当前问题相关的局部表/字段/指标，
旧链路（模板命中时直接用模板 SQL，模板未命中时走全量 schema prompt）。
下表展示新链路 `schema_context` trace step 中实际可见的规模。

| question | 新链路 tables | 新链路 fields | 新链路 metrics | 旧链路 tables_used | 旧链路 columns |
|---|---:|---:|---:|---:|---:|
| 2026 年 6 月 GMV 是多少？ | 4 | 45 | 1 | 1 | 1 |
| 2026 年 6 月净收入是多少？ | 4 | 45 | 1 | 1 | 1 |
| 2026 年 6 月商品销售额 Top 5 | 5 | 82 | 2 | 3 | 2 |
| DELETE FROM refunds WHERE id = 1 | 0 | 0 | 0 | 0 | 0 |
| DROP TABLE orders | 0 | 0 | 0 | 0 | 0 |
| JUNE_FIXED_50 在哪个渠道使用最多？ | 8 | 85 | 1 | 4 | 2 |
| 一级类目销售额排名 | 6 | 88 | 2 | 4 | 2 |
| 哪个设备类型加购到支付转化率最高？ | 7 | 99 | 2 | 1 | 2 |
| 查询 JUNE_FIXED_50 优惠券基本信息 | 7 | 72 | 1 | 1 | 8 |
| 查询 active 商品列表前 10 条 | 7 | 102 | 0 | 1 | 9 |

## 3. 多表 JoinPath 示例

### 2026 年 6 月 GMV 是多少？

- JoinPath 数量：2
- 使用的 relation：orders_coupons, order_items_order, orders_coupons
- relations 详情：order_items_order, orders_coupons
- 旧链路 tables：orders
- 新链路 tables：orders
- tables 一致：✓

### 2026 年 6 月净收入是多少？

- JoinPath 数量：2
- 使用的 relation：orders_coupons, order_items_order, orders_coupons
- relations 详情：order_items_order, orders_coupons
- 旧链路 tables：orders
- 新链路 tables：orders
- tables 一致：✓

## 4. Trace Steps 完整性

新 pipeline 每次请求应包含以下 9 个 trace step。表格标出缺失或失败的步骤。

| question | total_steps | failed_steps | missing_steps |
|---|---|---|---|
| 2026 年 6 月 GMV 是多少？ | 9 | — | — |
| 2026 年 6 月净收入是多少？ | 9 | — | — |
| 2026 年 6 月商品销售额 Top 5 | 9 | — | — |
| DELETE FROM refunds WHERE id = 1 | 0 | — | schema_retrieval, schema_context, join_path, query_plan, plan_validation, sql_generation, sql_guard, sql_execution, chart_decision |
| DROP TABLE orders | 0 | — | schema_retrieval, schema_context, join_path, query_plan, plan_validation, sql_generation, sql_guard, sql_execution, chart_decision |
| JUNE_FIXED_50 在哪个渠道使用最多？ | 9 | — | — |
| 一级类目销售额排名 | 9 | — | — |
| 哪个设备类型加购到支付转化率最高？ | 9 | — | — |
| 查询 JUNE_FIXED_50 优惠券基本信息 | 9 | — | — |
| 查询 active 商品列表前 10 条 | 9 | — | — |

## 5. Issue Tags 对比

| question | 旧链路 issue_tags | 新链路 issue_tags | 旧链路 SQL 预览 | 新链路 SQL 预览 |
|---|---|---|---|---|
| 2026 年 6 月 GMV 是多少？ | — | — | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o. | SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.created_at >= '2026-06-01' AND order |
| 2026 年 6 月净收入是多少？ | — | — | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_at >= '2026-06-01' A | SELECT SUM(orders.actual_amount) AS net_revenue FROM orders WHERE orders.created_at BETWEEN '2026-06 |
| 2026 年 6 月商品销售额 Top 5 | — | — | SELECT p.product_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_items oi JOIN orders o O | SELECT oi.product_name_snapshot, SUM(oi.line_amount) AS item_gmv FROM order_items oi INNER JOIN orde |
| DELETE FROM refunds WHERE id = 1 | sql_guard_blocked | — | DELETE FROM refunds WHERE id = 1 | DELETE FROM refunds WHERE id = 1 |
| DROP TABLE orders | sql_guard_blocked | — | DROP TABLE orders | DROP TABLE orders |
| JUNE_FIXED_50 在哪个渠道使用最多？ | — | — | SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count FROM coupons cp JOIN order_coupons oc ON  | SELECT c.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM orders o JOIN order_coupons oc ON o. |
| 一级类目销售额排名 | — | — | SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM product_categories p | SELECT pc.name, SUM(oi.line_amount) AS sales FROM order_items oi JOIN orders o ON oi.order_id = o.id |
| 哪个设备类型加购到支付转化率最高？ | — | — | SELECT device_type, ROUND(SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / NU | SELECT device_type, COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END) * 1.0 / NULLIF(COUNT( |
| 查询 JUNE_FIXED_50 优惠券基本信息 | — | — | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from,  | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from,  |
| 查询 active 商品列表前 10 条 | — | — | SELECT id, sku, product_name, category, status, price, launched_at, created_at, updated_at FROM prod | SELECT products.id, products.product_name, products.status, products.price, products.category FROM p |

## 6. 分 Case 明细

| question | 旧链路状态 | 新链路状态 | 旧 sql_preview | 新 sql_preview | 新 trace_steps 数 |
|---|---|---|---:|---:|
| 2026 年 6 月 GMV 是多少？ | passed | passed | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= : | SELECT SUM(orders.order_amount) AS gmv FROM orders WHERE orders.created_at >= '2 | 9 |
| 2026 年 6 月净收入是多少？ | passed | passed | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_ | SELECT SUM(orders.actual_amount) AS net_revenue FROM orders WHERE orders.created | 9 |
| 2026 年 6 月商品销售额 Top 5 | passed | passed | SELECT p.product_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_item | SELECT oi.product_name_snapshot, SUM(oi.line_amount) AS item_gmv FROM order_item | 9 |
| DELETE FROM refunds WHERE id = 1 | blocked | blocked | DELETE FROM refunds WHERE id = 1 | DELETE FROM refunds WHERE id = 1 | 0 |
| DROP TABLE orders | blocked | blocked | DROP TABLE orders | DROP TABLE orders | 0 |
| JUNE_FIXED_50 在哪个渠道使用最多？ | passed | passed | SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count FROM coupons cp JOIN  | SELECT c.channel_name, COUNT(DISTINCT o.id) AS usage_count FROM orders o JOIN or | 9 |
| 一级类目销售额排名 | passed | passed | SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM  | SELECT pc.name, SUM(oi.line_amount) AS sales FROM order_items oi JOIN orders o O | 9 |
| 哪个设备类型加购到支付转化率最高？ | passed | passed | SELECT device_type, ROUND(SUM(CASE WHEN event_type = 'payment_success' THEN 1 EL | SELECT device_type, COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END) * | 9 |
| 查询 JUNE_FIXED_50 优惠券基本信息 | passed | passed | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount,  | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount,  | 9 |
| 查询 active 商品列表前 10 条 | passed | passed | SELECT id, sku, product_name, category, status, price, launched_at, created_at,  | SELECT products.id, products.product_name, products.status, products.price, prod | 9 |