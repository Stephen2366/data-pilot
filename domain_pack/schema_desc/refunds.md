# refunds

## 业务含义

退款事实表，用于统计退款金额、退款原因、退款状态和商品退款率。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 退款主键 | join_key | normal |
| refund_no | 退款单号 | identifier | normal |
| source_order_no | 源系统订单号，格式 SRC-*，仅供外部追溯；退款关联订单必须使用 order_id，不能与 orders.order_no 直接 join | identifier | normal |
| order_id | 关联订单 | join_key | normal |
| order_item_id | 关联订单明细，可为空 | join_key | normal |
| user_id | 退款用户 | join_key | normal |
| product_id | 退款商品；整单退款缺少 order_item_id 时的兼容归因字段 | join_key | normal |
| refund_status | 退款状态：requested / approved / rejected / completed | filter | normal |
| refund_reason | 退款原因 | dimension | normal |
| refund_amount | 退款金额 | metric | normal |
| requested_at | 申请退款时间 | time | normal |
| processed_at | 处理完成时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 指标口径

- 退款率：成交订单范围内的 `refund_count / order_count`。商品维度优先用 `order_item_id -> order_items.product_id`，整单退款的 `order_item_id` 为空时回退 `refunds.product_id`；不能用 INNER JOIN 丢弃整单退款。
- 实际净退款金额：按 `processed_at` 落在查询窗口、且 `refund_status = 'completed'` 的 `SUM(refund_amount)`；负数表示冲销修正，必须保留负号，不能取绝对值。
- Top 退款原因锚点：`quality_issue`。

## 关联关系

- refunds.order_id -> orders.id
- refunds.order_item_id -> order_items.id
- refunds.user_id -> users.id
- refunds.product_id -> products.id

## 数据质量说明

- `order_item_id` 可为空，用于整单退款或历史兼容退款。
- 少量 `refund_amount` 为负数，表示冲销修正，计算总退款额时不要默认取绝对值。
