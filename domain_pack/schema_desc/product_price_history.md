# product_price_history

## 业务含义

商品价格历史表，使用 SCD Type 2 表达一个商品在不同时间窗口内的售价。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 价格版本主键 | join_key | normal |
| product_id | 关联商品 | join_key | normal |
| price | 该时间窗口内的售价 | metric | normal |
| valid_from | 价格生效时间 | time | normal |
| valid_to | 价格失效时间，NULL 表示当前价 | time | normal |
| is_current | 是否当前价格版本 | filter | normal |
| price_source | 价格来源 | dimension | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- product_price_history.product_id -> products.id

## 指标口径

- 查询历史售价时用 `target_time >= valid_from AND (target_time < valid_to OR valid_to IS NULL)`。
- 查询当前标价优先用 `products.price`。
