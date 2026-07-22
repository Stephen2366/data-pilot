# order_items

## 业务含义

订单明细事实表，一笔订单可以有多条商品明细。商品维度 GMV、销量和退款率默认优先使用这张表。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 订单明细主键 | join_key | normal |
| order_id | 关联订单头 | join_key | normal |
| product_id | 明细商品 | join_key | normal |
| line_no | 订单内行号 | dimension | normal |
| quantity | 明细购买件数 | metric | normal |
| unit_price | 下单时商品单价 | metric | normal |
| line_amount | 明细标价金额，quantity * unit_price | metric | normal |
| item_discount_amount | 分摊到明细的商品优惠 | metric | normal |
| item_actual_amount | 明细实付金额 | metric | normal |
| sku_snapshot | 下单时 SKU 快照 | dimension | normal |
| product_name_snapshot | 下单时商品名快照 | dimension | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- order_items.order_id -> orders.id
- order_items.product_id -> products.id
- refunds.order_item_id -> order_items.id

## 指标口径

- 商品维度 GMV：`SUM(order_items.line_amount)`，并关联 `orders` 过滤已支付且未取消订单。
- 统计订单量时若 join 明细表，必须 `COUNT(DISTINCT orders.id)`。
