# Phase 3A 新旧链路对照报告

- 生成时间：2026-07-26 17:20:07
- 共同 case 数：22
- 仅在 baseline 中出现：0
- 仅在新 pipeline 中出现：4

## 1. 通过率对比

| 指标 | 旧链路 (baseline) | 新链路 (new_text2sql) | 变化 |
|---|---:|---:|---|
| passed | 20 | 17 | -3 |
| blocked | 2 | 5 | +3 |
| error | 0 | 0 | 0 |
| 通过率 | 20/22 (91%) | 17/22 (77%) | — |

## 2. Schema 精简度对比

新链路通过 M9 Schema Retrieval 只给 LLM 看当前问题相关的局部表/字段/指标，
旧链路（模板命中时直接用模板 SQL，模板未命中时走全量 schema prompt）。
下表展示新链路 `schema_context` trace step 中实际可见的规模。

| question | 新链路 tables | 新链路 fields | 新链路 metrics | 旧链路 tables_used | 旧链路 columns |
|---|---:|---:|---:|---:|---:|
| 2026 年 6 月 GMV 是多少？ | 4 | 45 | 1 | 1 | 1 |
| 2026 年 6 月净收入是多少？ | 4 | 45 | 1 | 1 | 1 |
| 2026 年 6 月各商品平均售价是多少？ | 4 | 47 | 1 | 2 | 2 |
| 2026 年 6 月各渠道 GMV 排名 | 5 | 84 | 2 | 1 | 1 |
| 2026 年 6 月各渠道退款率排名 | 5 | 59 | 1 | 3 | 4 |
| 2026 年 6 月商品退款率排名，优先按订单明细归因 | 4 | 52 | 1 | 3 | 4 |
| 2026 年 6 月商品销售额 Top 5 | 5 | 82 | 2 | 3 | 2 |
| 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？ | 5 | 80 | 2 | 1 | 1 |
| 2026 年 6 月退款率最高的商品是什么？ | 4 | 52 | 1 | 3 | 4 |
| DELETE FROM refunds WHERE id = 1 | 0 | 0 | 0 | 0 | 0 |
| DROP TABLE orders | 0 | 0 | 0 | 0 | 0 |
| JUNE_FIXED_50 在哪个渠道使用最多？ | 8 | 85 | 1 | 4 | 2 |
| 一级类目销售额排名 | 6 | 88 | 2 | 4 | 2 |
| 各优惠券类型带来的 GMV 是多少？ | 7 | 97 | 2 | 1 | 1 |
| 各渠道订单量是多少？ | 7 | 101 | 2 | 2 | 2 |
| 哪个设备类型加购到支付转化率最高？ | 7 | 99 | 2 | 1 | 2 |
| 数码电子及其子类目 2026 年 6 月 GMV 是多少？ | 7 | 98 | 2 | 1 | 1 |
| 查询 2026 年 6 月已支付订单 | 6 | 89 | 2 | 1 | 16 |
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
| 2026 年 6 月各商品平均售价是多少？ | 9 | — | — |
| 2026 年 6 月各渠道 GMV 排名 | 9 | — | — |
| 2026 年 6 月各渠道退款率排名 | 9 | — | — |
| 2026 年 6 月商品退款率排名，优先按订单明细归因 | 5 | plan_validation | sql_generation, sql_guard, sql_execution, chart_decision |
| 2026 年 6 月商品销售额 Top 5 | 9 | — | — |
| 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？ | 9 | — | — |
| 2026 年 6 月退款率最高的商品是什么？ | 9 | — | — |
| DELETE FROM refunds WHERE id = 1 | 0 | — | schema_retrieval, schema_context, join_path, query_plan, plan_validation, sql_generation, sql_guard, sql_execution, chart_decision |
| DROP TABLE orders | 0 | — | schema_retrieval, schema_context, join_path, query_plan, plan_validation, sql_generation, sql_guard, sql_execution, chart_decision |
| JUNE_FIXED_50 在哪个渠道使用最多？ | 9 | — | — |
| 一级类目销售额排名 | 9 | — | — |
| 各优惠券类型带来的 GMV 是多少？ | 9 | — | — |
| 各渠道订单量是多少？ | 9 | — | — |
| 哪个设备类型加购到支付转化率最高？ | 9 | — | — |
| 数码电子及其子类目 2026 年 6 月 GMV 是多少？ | 7 | sql_guard | sql_execution, chart_decision |
| 查询 2026 年 6 月已支付订单 | 9 | — | — |
| 查询 JUNE_FIXED_50 优惠券基本信息 | 9 | — | — |
| 查询 active 商品列表前 10 条 | 9 | — | — |

## 5. Issue Tags 对比

| question | 旧链路 issue_tags | 新链路 issue_tags | 旧链路 SQL 预览 | 新链路 SQL 预览 |
|---|---|---|---|---|
| 2026 年 6 月 GMV 是多少？ | — | — | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o. | SELECT SUM(order_amount) AS gmv FROM orders WHERE order_status NOT IN ('cancelled', 'canceled') AND  |
| 2026 年 6 月净收入是多少？ | — | — | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_at >= '2026-06-01' A | SELECT SUM(actual_amount) AS net_revenue FROM orders WHERE paid_at BETWEEN '2026-06-01' AND '2026-06 |
| 2026 年 6 月各商品平均售价是多少？ | — | — | SELECT p.product_name, AVG(pph.price) AS avg_selling_price FROM products p JOIN product_price_histor | SELECT p.product_name, AVG(ph.price) AS avg_selling_price FROM product_price_history ph INNER JOIN p |
| 2026 年 6 月各渠道 GMV 排名 | — | — | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o. | SELECT c.channel_code, c.channel_name, SUM(o.order_amount) AS gmv FROM orders o JOIN channels c ON o |
| 2026 年 6 月各渠道退款率排名 | — | — | SELECT c.channel_name, COUNT(DISTINCT r.id) AS refund_count, COUNT(DISTINCT o.id) AS order_count, RO | SELECT c.channel_name, COUNT(DISTINCT r.order_id) * 1.0 / COUNT(DISTINCT o.id) AS refund_rate FROM o |
| 2026 年 6 月商品退款率排名，优先按订单明细归因 | — | plan_validation_failed | SELECT p.product_name, COUNT(DISTINCT o.id) AS order_count, COUNT(DISTINCT r.id) AS refund_count, RO |  |
| 2026 年 6 月商品销售额 Top 5 | — | — | SELECT p.product_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_items oi JOIN orders o O | SELECT p.product_name, SUM(oi.line_amount) AS item_gmv
FROM order_items oi
INNER JOIN orders o ON oi |
| 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？ | — | — | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_at >= '2026-06-01' A | SELECT SUM(actual_amount) AS total_actual_amount FROM orders WHERE paid_at >= '2026-06-01' AND paid_ |
| 2026 年 6 月退款率最高的商品是什么？ | — | — | SELECT
  p.product_name,
  COUNT(DISTINCT r.id) AS refund_count,
  COUNT(DISTINCT o.id) AS order_cou | SELECT p.id, p.product_name, CASE WHEN COUNT(DISTINCT o.id) = 0 THEN 0 ELSE CAST(COUNT(DISTINCT CASE |
| DELETE FROM refunds WHERE id = 1 | sql_guard_blocked | — | DELETE FROM refunds WHERE id = 1 | DELETE FROM refunds WHERE id = 1 |
| DROP TABLE orders | sql_guard_blocked | — | DROP TABLE orders | DROP TABLE orders |
| JUNE_FIXED_50 在哪个渠道使用最多？ | — | — | SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count FROM coupons cp JOIN order_coupons oc ON  | SELECT channels.channel_name, COUNT(DISTINCT orders.id) AS usage_count FROM orders JOIN channels ON  |
| 一级类目销售额排名 | — | — | SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM product_categories p | SELECT pc.name AS category_name, SUM(oi.line_amount) AS item_gmv FROM order_items oi INNER JOIN orde |
| 各优惠券类型带来的 GMV 是多少？ | — | — | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o. | SELECT sub.coupon_type, SUM(sub.order_amount) AS GMV FROM (SELECT DISTINCT coupons.coupon_type, orde |
| 各渠道订单量是多少？ | — | — | SELECT
  c.channel_name,
  COUNT(o.id) AS order_count
FROM channels c
JOIN orders o ON o.channel_id  | SELECT c.channel_name, COUNT(o.id) AS order_count FROM orders o INNER JOIN channels c ON o.channel_i |
| 哪个设备类型加购到支付转化率最高？ | — | — | SELECT device_type, ROUND(SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / NU | SELECT device_type, (COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END) * 1.0 / COUNT(CASE W |
| 数码电子及其子类目 2026 年 6 月 GMV 是多少？ | — | sql_guard_blocked | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o. | WITH RECURSIVE category_tree AS (
    SELECT id FROM product_categories WHERE name = '数码电子'
    UNIO |
| 查询 2026 年 6 月已支付订单 | — | — | SELECT * FROM orders WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' AND order_status NOT I | SELECT order_no, order_amount, actual_amount, discount_amount, shipping_amount, order_status, paid_a |
| 查询 JUNE_FIXED_50 优惠券基本信息 | — | — | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount, status, valid_from,  | SELECT coupons.coupon_code, coupons.coupon_name, coupons.coupon_type, coupons.created_at, coupons.di |
| 查询 active 商品列表前 10 条 | — | — | SELECT id, sku, product_name, category, status, price, launched_at, created_at, updated_at FROM prod | SELECT product_name, category, status FROM products WHERE status = 'active' LIMIT 10 |
| 查询所有管理员用户的联系方式 | — | — | SELECT id, user_name, role, status FROM users WHERE role = 'admin' | SELECT email, phone, user_name FROM users WHERE role = '管理员' |
| 查询用户邮箱和手机号 | — | plan_validation_failed | SELECT id, user_name, role, status, created_at, updated_at FROM users LIMIT 0 |  |

## 6. 分 Case 明细

| question | 旧链路状态 | 新链路状态 | 旧 sql_preview | 新 sql_preview | 新 trace_steps 数 |
|---|---|---|---:|---:|
| 2026 年 6 月 GMV 是多少？ | passed | passed | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= : | SELECT SUM(order_amount) AS gmv FROM orders WHERE order_status NOT IN ('cancelle | 9 |
| 2026 年 6 月净收入是多少？ | passed | passed | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_ | SELECT SUM(actual_amount) AS net_revenue FROM orders WHERE paid_at BETWEEN '2026 | 9 |
| 2026 年 6 月各商品平均售价是多少？ | passed | passed | SELECT p.product_name, AVG(pph.price) AS avg_selling_price FROM products p JOIN  | SELECT p.product_name, AVG(ph.price) AS avg_selling_price FROM product_price_his | 9 |
| 2026 年 6 月各渠道 GMV 排名 | passed | passed | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= : | SELECT c.channel_code, c.channel_name, SUM(o.order_amount) AS gmv FROM orders o  | 9 |
| 2026 年 6 月各渠道退款率排名 | passed | passed | SELECT c.channel_name, COUNT(DISTINCT r.id) AS refund_count, COUNT(DISTINCT o.id | SELECT c.channel_name, COUNT(DISTINCT r.order_id) * 1.0 / COUNT(DISTINCT o.id) A | 9 |
| 2026 年 6 月商品退款率排名，优先按订单明细归因 | passed | blocked | SELECT p.product_name, COUNT(DISTINCT o.id) AS order_count, COUNT(DISTINCT r.id) |  | 5 |
| 2026 年 6 月商品销售额 Top 5 | passed | passed | SELECT p.product_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM order_item | SELECT p.product_name, SUM(oi.line_amount) AS item_gmv
FROM order_items oi
INNER | 9 |
| 2026 年 6 月已支付订单的实收金额（actual_amount 总和）是多少？ | passed | passed | SELECT ROUND(SUM(o.actual_amount), 2) AS net_revenue FROM orders o WHERE o.paid_ | SELECT SUM(actual_amount) AS total_actual_amount FROM orders WHERE paid_at >= '2 | 9 |
| 2026 年 6 月退款率最高的商品是什么？ | passed | passed | SELECT
  p.product_name,
  COUNT(DISTINCT r.id) AS refund_count,
  COUNT(DISTINC | SELECT p.id, p.product_name, CASE WHEN COUNT(DISTINCT o.id) = 0 THEN 0 ELSE CAST | 9 |
| DELETE FROM refunds WHERE id = 1 | blocked | blocked | DELETE FROM refunds WHERE id = 1 | DELETE FROM refunds WHERE id = 1 | 0 |
| DROP TABLE orders | blocked | blocked | DROP TABLE orders | DROP TABLE orders | 0 |
| JUNE_FIXED_50 在哪个渠道使用最多？ | passed | passed | SELECT c.channel_name, COUNT(DISTINCT o.id) AS order_count FROM coupons cp JOIN  | SELECT channels.channel_name, COUNT(DISTINCT orders.id) AS usage_count FROM orde | 9 |
| 一级类目销售额排名 | passed | passed | SELECT pc.name AS category_name, ROUND(SUM(oi.line_amount), 2) AS item_gmv FROM  | SELECT pc.name AS category_name, SUM(oi.line_amount) AS item_gmv FROM order_item | 9 |
| 各优惠券类型带来的 GMV 是多少？ | passed | passed | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= : | SELECT sub.coupon_type, SUM(sub.order_amount) AS GMV FROM (SELECT DISTINCT coupo | 9 |
| 各渠道订单量是多少？ | passed | passed | SELECT
  c.channel_name,
  COUNT(o.id) AS order_count
FROM channels c
JOIN order | SELECT c.channel_name, COUNT(o.id) AS order_count FROM orders o INNER JOIN chann | 9 |
| 哪个设备类型加购到支付转化率最高？ | passed | passed | SELECT device_type, ROUND(SUM(CASE WHEN event_type = 'payment_success' THEN 1 EL | SELECT device_type, (COUNT(CASE WHEN event_type = 'payment_success' THEN 1 END)  | 9 |
| 数码电子及其子类目 2026 年 6 月 GMV 是多少？ | passed | blocked | SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= : | WITH RECURSIVE category_tree AS (
    SELECT id FROM product_categories WHERE na | 7 |
| 查询 2026 年 6 月已支付订单 | passed | passed | SELECT * FROM orders WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' AN | SELECT order_no, order_amount, actual_amount, discount_amount, shipping_amount,  | 9 |
| 查询 JUNE_FIXED_50 优惠券基本信息 | passed | passed | SELECT coupon_code, coupon_name, coupon_type, discount_value, min_order_amount,  | SELECT coupons.coupon_code, coupons.coupon_name, coupons.coupon_type, coupons.cr | 9 |
| 查询 active 商品列表前 10 条 | passed | passed | SELECT id, sku, product_name, category, status, price, launched_at, created_at,  | SELECT product_name, category, status FROM products WHERE status = 'active' LIMI | 9 |
| 查询所有管理员用户的联系方式 | passed | passed | SELECT id, user_name, role, status FROM users WHERE role = 'admin' | SELECT email, phone, user_name FROM users WHERE role = '管理员' | 9 |
| 查询用户邮箱和手机号 | passed | blocked | SELECT id, user_name, role, status, created_at, updated_at FROM users LIMIT 0 |  | 5 |