# orders_wide

## 业务含义

订单宽表快照，把订单、用户、商品和渠道的常用字段冗余到一张表，适合看板汇总。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 宽表主键 | join_key | normal |
| order_id | 源订单 ID | join_key | normal |
| order_no | 订单号 | identifier | normal |
| source_order_no | 源系统订单号，可能重复 | identifier | normal |
| external_order_no | 外部平台订单号，可能重复 | identifier | normal |
| user_id | 用户 ID | join_key | normal |
| user_name | 用户展示名快照 | dimension | normal |
| user_status | 用户状态快照 | filter | normal |
| product_id | 主商品 ID | join_key | normal |
| sku | 主商品 SKU 快照 | dimension | normal |
| product_name | 主商品名快照 | dimension | normal |
| category_id | 主商品类目 ID | join_key | normal |
| category | 一级类目冗余字段 | dimension | normal |
| channel_id | 渠道 ID | join_key | normal |
| channel_code | 渠道编码 | dimension | normal |
| channel_name | 渠道名称 | dimension | normal |
| channel_type | 渠道类型 | dimension | normal |
| order_status | 订单状态 | filter | normal |
| order_amount | 订单 GMV 金额 | metric | normal |
| shipping_amount | 运费 | metric | normal |
| discount_amount | 订单优惠总额 | metric | normal |
| actual_amount | 实付金额 | metric | normal |
| quantity | 订单商品件数 | metric | normal |
| paid_at | 支付时间，可为空 | time | normal |
| source_updated_at | 源订单更新时间 | time | normal |
| snapshot_at | 宽表快照时间 | time | normal |
| batch_id | 快照批次 | dimension | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- orders_wide.order_id -> orders.id

## 指标口径

- 宽表适合渠道 GMV、渠道订单量等看板聚合；明细追溯、优惠券、多商品和强一致校验回到规范化表。
