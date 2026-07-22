# coupons

## 业务含义

优惠券维表，记录券码、券类型、优惠面额和有效期。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 优惠券主键 | join_key | normal |
| coupon_code | 稳定券码 | identifier | normal |
| coupon_name | 优惠券名称 | dimension | normal |
| coupon_type | 券类型：fixed_amount / free_shipping / percentage | filter | normal |
| discount_value | 优惠面额或折扣点数 | metric | normal |
| min_order_amount | 最低使用门槛 | metric | normal |
| status | 优惠券状态 | filter | normal |
| valid_from | 生效时间 | time | normal |
| valid_to | 失效时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 关联关系

- order_coupons.coupon_id -> coupons.id

## 指标口径

- 优惠券使用率按 `order_coupons` 关联订单统计，一单多券时订单量必须去重。
