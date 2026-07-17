# refunds

## 业务含义

退款事实表，用于统计退款金额、退款原因、退款状态和商品退款率。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 退款主键 | join_key | normal |
| refund_no | 退款单号 | identifier | normal |
| order_id | 关联订单 | join_key | normal |
| user_id | 退款用户 | join_key | normal |
| product_id | 退款商品 | join_key | normal |
| refund_status | 退款状态：requested / approved / rejected / completed | filter | normal |
| refund_reason | 退款原因 | dimension | normal |
| refund_amount | 退款金额 | metric | normal |
| requested_at | 申请退款时间 | time | normal |
| processed_at | 处理完成时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 指标口径

- 退款率：`refund_count / order_count`，商品维度通常按 `product_id` 关联订单计算。
- Top 退款原因锚点：`quality_issue`。
