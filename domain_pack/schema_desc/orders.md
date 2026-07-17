# orders

## 业务含义

订单事实表，是 GMV、订单量、渠道表现和商品表现的核心数据源。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 订单主键 | join_key | normal |
| order_no | 订单号 | identifier | normal |
| user_id | 下单用户 | join_key | normal |
| product_id | 商品 | join_key | normal |
| channel_id | 渠道 | join_key | normal |
| order_status | 订单状态：paid / shipped / delivered / cancelled | filter | normal |
| order_amount | 订单金额，GMV 的基础字段 | metric | normal |
| quantity | 购买件数 | metric | normal |
| paid_at | 支付时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 指标口径

- GMV：`sum(order_amount)`，一般排除 `order_status = 'cancelled'`。
- 订单量：`count(distinct orders.id)`。
