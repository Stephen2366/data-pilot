# order_coupons

## 业务含义

订单与优惠券的桥接表，表达一笔订单使用了哪些优惠券以及每张券抵扣了多少金额。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 桥接记录主键 | join_key | normal |
| order_id | 关联订单 | join_key | normal |
| coupon_id | 关联优惠券 | join_key | normal |
| discount_amount | 本张券抵扣金额 | metric | normal |
| applied_at | 用券时间 | time | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- order_coupons.order_id -> orders.id
- order_coupons.coupon_id -> coupons.id

## 指标口径

- 一单可用多张券，按订单统计时使用 `COUNT(DISTINCT orders.id)`。
