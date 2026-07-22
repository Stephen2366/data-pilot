# orders_wide

## 业务含义

订单宽表快照，把订单、用户、商品和渠道的常用字段冗余到一张表，适合看板汇总。

## 粒度

一行对应一笔源订单快照，`order_id` 与 `orders.id` 一一对应。多商品订单会通过
`item_count` 标记明细行数，但宽表只保留主商品快照。

## 何时使用

- 渠道 GMV、渠道订单量、主商品维度趋势等看板汇总。
- 需要快速判断“是否有退款”“退款单数”“退款金额”的粗粒度看板。

## 何时避免

- 商品明细 GMV、优惠券多对多分析、金额一致性诊断、退款明细归因。
- 需要最新强一致事实时，优先回到 `orders` / `order_items` / `refunds` 星型模型。

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
| user_role | 用户角色快照 | filter | normal |
| product_id | 主商品 ID | join_key | normal |
| sku | 主商品 SKU 快照 | dimension | normal |
| product_name | 主商品名快照 | dimension | normal |
| primary_product_price | 主商品当前价快照 | metric | normal |
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
| item_count | 订单明细行数 | metric | normal |
| refund_count | 退款单数快照 | metric | normal |
| total_refund | 退款金额快照 | metric | normal |
| has_refund | 是否发生退款 | filter | normal |
| paid_at | 支付时间，可为空 | time | normal |
| source_updated_at | 源订单更新时间 | time | normal |
| snapshot_at | 宽表快照时间 | time | normal |
| batch_id | 快照批次 | dimension | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 宽表记录更新时间 | time | normal |

## 关联关系

- orders_wide.order_id -> orders.id

## 指标口径

- 宽表适合渠道 GMV、渠道订单量、退款订单数等看板聚合。
- `refund_count` / `total_refund` / `has_refund` 是 seed 生成时的快照口径，实时追溯仍回到 `refunds`。

## 数据质量说明

- `orders_wide` 是快照表，`snapshot_at` 代表抽取时间；和星型模型对账时要接受“可能延迟”的业务语义。
- `quantity` 是订单头件数，`item_count` 是明细行数，二者不是同一概念。
