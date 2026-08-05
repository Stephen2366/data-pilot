# orders

## 业务含义

订单事实表，是 GMV、订单量、渠道表现和商品表现的核心数据源。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 订单主键 | join_key | normal |
| order_no | 订单号 | identifier | normal |
| source_order_no | 源系统订单号，可能重复，格式 SRC-2026-*；不能与 order_no 的 ORD-2026-* 直接 join | identifier | normal |
| external_order_no | 外部平台订单号，可能重复，不是订单主键 | identifier | normal |
| user_id | 下单用户 | join_key | normal |
| product_id | 商品 | join_key | normal |
| channel_id | 渠道 | join_key | normal |
| order_status | 订单状态：paid / shipped / delivered / cancelled / canceled / pending_payment；成交口径排除两种取消状态并要求 paid_at 非空 | filter | normal |
| order_amount | 订单金额，GMV 的基础字段 | metric | normal |
| shipping_amount | 运费金额 | metric | normal |
| discount_amount | 订单优惠总额 | metric | normal |
| actual_amount | 实付金额，order_amount + shipping_amount - discount_amount | metric | normal |
| quantity | 购买件数 | metric | normal |
| paid_at | 支付时间，可为空 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 指标口径

- GMV：`sum(order_amount)`，默认排除 `order_status IN ('cancelled', 'canceled')` 且 `paid_at IS NOT NULL`。
- 订单量：`count(distinct orders.id)`；直接查 orders 时可与 `count(orders.id)` 等价，join 明细、退款或优惠券后必须去重。
- 净收入 / 实付金额：`sum(actual_amount)`。
- 商品维度 GMV / 销量默认走 `order_items`，`orders.product_id` 只保留主商品兼容口径。

## 关联关系

- orders.user_id -> users.id
- orders.product_id -> products.id
- orders.channel_id -> channels.id
- order_items.order_id -> orders.id
- order_coupons.order_id -> orders.id
- orders_wide.order_id -> orders.id

## 数据质量说明

- 约 20 条订单 `paid_at IS NULL`，计算 GMV 时必须排除。
- 少量订单使用 `canceled` 单 l 拼写，统计取消订单时需要兼容。
- `source_order_no` / `external_order_no` 故意有逻辑重复，不破坏 `order_no` 唯一约束；`source_order_no` 的 SRC 命名空间不能与 `order_no` 的 ORD 命名空间直接 join。
